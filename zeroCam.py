# -*- coding: utf-8 -*-

import logging
import logging.handlers
import os
import sys
import json
import time
import threading
import traceback
import datetime

import schedule
from flask import has_request_context, request

# Importa i componenti modularizzati
from lib.components.config_manager import ConfigManager
from lib.components.mqtt_manager import MQTTManager
from lib.components.stats_collector import StatsCollector
from lib.components.component_manager import ComponentManager
from lib.components.scheduler_manager import SchedulerManager
from lib.netwatch import NetworkWatchdog
from lib import mdns

# Importa le funzioni di supporto ancora necessarie
from lib.helpers import (
    logRecursive,
    unsharpMask,
    check_internet_connection,
    get_raspberry_pi_stats,
    saveImage
)
from cameras import AWB_MANUAL
from lib import exif, paths
from lib.version import get_version
from settingsManager import run_settings_manager

# --- Global Exception Handler ---
def unhandled_exception_handler(exc_type, exc_value, exc_traceback):
    """Catches all unhandled exceptions, logs them, and exits."""
    tb = ''.join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    logging.getLogger("zeroCam").critical(f"Unhandled exception, forcing shutdown:\n{tb}")
    os._exit(1) # Force exit to be restarted by a supervisor

sys.excepthook = unhandled_exception_handler

class ZeroCamApp:
    """
    The main application orchestrator.
    It initializes and coordinates all manager components.
    """
    def __init__(self, device_id, logger):
        self.device_id = device_id
        self.logger = logger
        self.logger.propagate = False
        self.threads = []
        
        # Core application state
        self.shot_counter = 0
        self.capture_started_at = None
        self.diagnostic_data = {}
        self.streaming_was_active = False

        # Threading and concurrency controls
        self.shutdown_flag = threading.Event()
        self.shutdown_lock = threading.Lock()
        self.capture_lock = threading.Lock()
        self.hard_reset_lock = threading.Lock()
        self.capture_active = threading.Event()
        self.capture_active.set()

        # Initialize Managers
        secret_key = os.getenv("ZEROCAM_SECRET_KEY")
        if not secret_key:
            self.logger.critical("ZEROCAM_SECRET_KEY environment variable not set. Exiting.")
            exit(1)
            
        self.config_manager = ConfigManager(self.logger, secret_key)
        self.components = ComponentManager(self.config_manager, self.logger)
        self.stats_collector = StatsCollector(self.logger)
        self.mqtt_manager = MQTTManager(self.device_id, self.config_manager.get("mqtt", {}), self.logger, self)
        self.scheduler_manager = SchedulerManager(self, self.logger)
        self.netwatch = NetworkWatchdog(
            self.config_manager.decrypted_config.get("network", {}), self.logger)

    def start(self):
        """Starts all application services."""
        self.logger.info("Starting ZeroCam application...")
        self.log_config()
        self.publish_diagnostic("Starting")
        
        # Start the Flask web server for settings
        flask_thread = threading.Thread(target=run_settings_manager, args=(self,), name="FlaskThread", daemon=True)
        flask_thread.start()
        self.threads.append(flask_thread)

        # Start the scheduler
        scheduler_thread = self.scheduler_manager.start()
        self.threads.append(scheduler_thread)

        # Il nome con cui la webcam compare sulla rete: dipende dalla
        # configurazione, quindi va riscritto qui e a ogni salvataggio.
        mdns.publish(self.config_manager.decrypted_config, self.logger)

        # Sorveglianza della rete: accende l'hotspot quando non ce n'è una.
        # Parte con tutto il resto e non dipende da nulla, perché il caso in
        # cui serve è proprio quello in cui il resto non funziona.
        self.threads.append(self.netwatch.start())

        # Start the thread supervisor
        supervisor_thread = threading.Thread(target=self.monitor_threads, name="SupervisorThread", daemon=True)
        supervisor_thread.start()
        self.threads.append(supervisor_thread)

        self.logger.info("ZeroCam startup complete. Main loop running.")

    def log_config(self):
        """Logs the initial configuration for debugging purposes."""
        self.logger.info("--- ZeroCam Configuration ---")
        self.logger.info(f"Device ID: {self.device_id}")
        logRecursive(self.logger, self.config_manager.config)
        self.logger.info("-----------------------------")

    def monitor_threads(self):
        """Monitors daemon threads and shuts down the application if one fails."""
        while not self.shutdown_flag.is_set():
            time.sleep(10)
            for thread in self.threads:
                if not thread.is_alive():
                    self.logger.critical(f"Thread '{thread.name}' has died! Initiating shutdown.")
                    self.shutdown()
                    return # Exit the monitor loop
    
    def trigger_capture(self):
        """Schedules an immediate capture job in a new thread."""
        self.logger.info("Manual capture triggered via MQTT command.")
        capture_thread = threading.Thread(target=self.capture_job, name="ManualCaptureThread")
        capture_thread.start()

    def capture_job(self):
        """The core logic for capturing, processing, and uploading an image."""
        with self.capture_lock:
            if not self.capture_active.is_set():
                self.logger.info("Capture is paused, skipping job.")
                return

            self.config_manager.load_config() # Refresh config before each capture
            self.publish_diagnostic("Capturing Image")

            day_period = self.components.day_period_calc.get_day_period()
            if day_period == "unknown":
                self.logger.error("Day period is 'unknown', skipping capture.")
                return

            self.logger.info(f"Capture started for day period: {day_period}")
            # Da qui in avanti la cattura è in corso: l'istante di inizio serve
            # all'interfaccia per dire da quanto sta lavorando, visto che di
            # notte il bracketing può durare minuti.
            self.capture_started_at = time.monotonic()
            try:
            
                # Stop stream if running
                if hasattr(self.components.camera, 'running') and self.components.camera.running:
                    self.components.camera.streamStop()

                image_buffer, metadata = self.components.camera.takePicture(day_period)
            
                if image_buffer is None:
                    self.logger.error("Failed to capture image (buffer is None).")
                    self.publish_diagnostic("Error: Capture Failed")
                    self._restart_stream_if_enabled(day_period)
                    return
            
                self.shot_counter += 1
                self.logger.info(f"Image captured successfully. Shot counter: {self.shot_counter}")

                if self.config_manager.get("cameraParameters", {}).get("unsharpMask", False):
                    self.publish_diagnostic("Applying unsharp mask")
                    unsharpMask(self.logger, image_buffer)

                self.publish_diagnostic("Annotating and Overlaying")
                self.logger.info(f"Crop settings: {self.components.cropper.crop_settings}")
                self.logger.info(f"Crop enabled: {self.components.cropper.crop_settings.get('enabled', 'Crop Not ENABLED')}")
                if self.components.cropper and self.components.cropper.crop_settings.get("enabled", False):
                    image_buffer = self.components.cropper.crop(image_buffer)

                if self.components.privacy_masker:
                    image_buffer = self.components.privacy_masker.apply_masks(image_buffer)

                image_buffer = self.components.annotator.annotate(image_buffer)
                image_buffer = self.components.overlay.add_overlays(image_buffer)

                # I metadati si rimettono qui, una volta sola: da questo punto
                # in avanti lo stesso buffer va all'FTP, all'upload HTTP,
                # all'immagine locale e all'archivio.
                description = (
                    f"{self.config_manager.get('deviceDetails', {}).get('name', 'zeroCAM')}"
                    f" - {day_period}"
                )
                manual_wb = self._manual_white_balance(day_period)
                image_buffer = exif.attach(
                    image_buffer, metadata, datetime.datetime.now(),
                    description=description, software=f"zeroCAM {get_version()}",
                    manual_white_balance=manual_wb,
                )

                self.publish_diagnostic("Uploading Image")
                self.components.ftp_uploader.upload(image_buffer, metadata)
                image_buffer.seek(0)
                self.components.http_uploader.upload(image_buffer, metadata)

                saveImage(self.logger, image_buffer) # Save latest image locally
                self._archive_image_if_enabled(image_buffer, metadata, day_period)
                # Fotogramma per il timelapse settimanale: immagine finale, già
                # ritagliata, mascherata e annotata come quella pubblicata. I
                # metadati della cattura lo accompagnano come EXIF.
                self.components.timelapse.store_frame(
                    image_buffer,
                    metadata=metadata,
                    description=description,
                    manual_white_balance=manual_wb,
                )

                self.publish_diagnostic("Capture Completed")
                self.logger.info(f"Capture job finished in {time.monotonic() - self.capture_started_at:.1f}s.")
                self.diagnostic_data["lastCapture"] = datetime.datetime.now().strftime("%d-%m-%Y %H:%M:%S")
                self.diagnostic_data["lastCapture_dayperiod"] = day_period
                time.sleep(1) # Small delay before status change
                self.publish_diagnostic("Idle")
            
                self._check_for_hard_reset()
                self._restart_stream_if_enabled(day_period)
            
            finally:
                elapsed = time.monotonic() - (self.capture_started_at or time.monotonic())
                self.capture_started_at = None
                self.logger.info(f"Capture cycle for '{day_period}' ended after {elapsed:.1f}s.")

    def _manual_white_balance(self, day_period):
        """True se la fase in corso ha il bilanciamento del bianco manuale."""
        phase = self.config_manager.get("cameraParameters", {}).get(day_period, {})
        try:
            return int(phase.get("AwbMode", 0)) == AWB_MANUAL
        except (TypeError, ValueError):
            return False

    def _archive_image_if_enabled(self, image_buffer, metadata, day_period):
        """Saves the image and metadata to a local archive if configured."""
        if not self.config_manager.get("cameraParameters", {}).get("archiveImages", False):
            return
        
        try:
            now = datetime.datetime.now()
            filename = now.strftime('%Y%m%d-%H%M%S')
            os.makedirs(paths.IMAGES_DIR, exist_ok=True)
            
            # Save image
            with open(os.path.join(paths.IMAGES_DIR, f'{filename}.jpg'), 'wb') as f:
                f.write(image_buffer.getvalue())
            
            # Save metadata
            day_info = self.components.day_period_calc
            archive_meta = {
                "day_info": {
                    "dayperiod": day_period,
                    "dawn": day_info.dawn.strftime("%d-%m-%Y %H:%M:%S"),
                    "sunrise": day_info.sunrise.strftime("%d-%m-%Y %H:%M:%S"),
                    "sunset": day_info.sunset.strftime("%d-%m-%Y %H:%M:%S"),
                    "dusk": day_info.dusk.strftime("%d-%m-%Y %H:%M:%S")
                },
                "image_metadata": metadata
            }
            with open(os.path.join(paths.IMAGES_DIR, f'{filename}.json'), 'w') as f:
                json.dump(archive_meta, f, indent=4)
        except Exception as e:
            self.logger.error(f"Failed to archive image: {e}", exc_info=True)

    def _check_for_hard_reset(self):
        """Performs a camera hard reset if the shot counter reaches the configured interval."""
        reset_interval = self.config_manager.get("cameraParameters", {}).get("hardResetInterval", 0)
        if reset_interval > 0 and self.shot_counter >= reset_interval:
            self.hard_reset_camera()

    def _restart_stream_if_enabled(self, day_period):
        """Restarts the YouTube stream if it's enabled in the config."""
        # Il broadcast va predisposto PRIMA che ffmpeg riprenda a pubblicare:
        # con enableAutoStart va in onda appena rileva l'ingest RTMP.
        if self.config_manager.get("streamParameters", {}).get("enabled", False):
            self.components.youtube_live.ensure_broadcast()
        self.components.camera.streamStart(day_period)

    def hard_reset_camera(self):
        """Closes and re-initializes the camera object completely."""
        with self.hard_reset_lock:
            self.logger.warning("Performing camera hard reset...")
            try:
                # Stop stream if running
                if hasattr(self.components.camera, 'running') and self.components.camera.running:
                    self.logger.info("Stopping stream for hard reset.")
                    self.components.camera.streamStop()
                
                # Close existing camera object
                if hasattr(self.components.camera, 'camera') and self.components.camera.camera:
                    self.components.camera.camera.close()
                    self.logger.info("Old camera object closed.")

                # Re-initialize camera using the ComponentManager's logic
                self.components._init_camera()
                self.logger.info("Camera re-initialized successfully.")
                self.shot_counter = 0
                self.logger.warning("Camera hard reset completed.")

            except Exception as e:
                self.logger.critical(f"Failed during camera hard reset: {e}. Shutting down.", exc_info=True)
                self.shutdown()

    def publish_diagnostic(self, device_status=None):
        """Compiles and publishes diagnostic data to MQTT."""
        if not self.mqtt_manager or not self.mqtt_manager.client:
            return

        self.diagnostic_data.update({
            "deviceDetails": self.config_manager.get("deviceDetails"),
            "hardwareStatus": get_raspberry_pi_stats(),
            "dayPeriod": self.components.day_period_calc.get_day_period(),
            "nextCapture": schedule.next_run.strftime("%d-%m-%Y %H:%M:%S") if schedule.next_run else "N/A",
        })
        if device_status:
            self.diagnostic_data["deviceStatus"] = device_status

        self.logger.debug(f"Publishing diagnostic data: {self.diagnostic_data}")
        self.mqtt_manager.publish("diagnostic", self.diagnostic_data)

    def shutdown(self):
        """Performs a controlled and reliable shutdown of the application."""
        if not self.shutdown_lock.acquire(blocking=False):
            self.logger.warning("Shutdown already in progress.")
            return

        self.logger.warning("Shutdown sequence initiated...")
        self.shutdown_flag.set()

        if hasattr(self.components.camera, 'running') and self.components.camera.running:
            self.logger.info("Stopping active stream before shutdown...")
            self.components.camera.streamStop()

        if self.config_manager.get("youtubeLive", {}).get("end_on_shutdown", False):
            self.components.youtube_live.end_broadcast()

        self.mqtt_manager.disconnect()
        
        self.logger.warning("Graceful shutdown complete. Exiting to trigger service restart.")
        os._exit(1)
        
    def pause_capture(self):
        """Pauses the main capture loop, typically for maintenance tasks like focus aid."""
        self.logger.info("Pausing main capture loop.")
        self.capture_active.clear()
        
        if self.components.camera and hasattr(self.components.camera, 'running') and self.components.camera.running:
            self.logger.info("Streaming is active, stopping it temporarily.")
            self.streaming_was_active = True
            self.components.camera.streamStop()
        else:
            self.streaming_was_active = False

    def resume_capture(self):
        """Resumes the main capture loop after being paused."""
        self.logger.info("Resuming main capture loop.")
        
        if self.streaming_was_active:
            self.logger.info("Waiting for focus aid to release the camera...")
            
            # Attendi attivamente che la camera venga fermata dal thread del focus aid
            wait_start_time = time.time()
            camera_object = self.components.camera.camera
            
            # Aggiungiamo un timeout di 5 secondi per sicurezza
            while hasattr(camera_object, 'started') and camera_object.started and (time.time() - wait_start_time) < 5:
                time.sleep(0.1)
            
            # Se la camera è ancora in esecuzione dopo il timeout, forziamo lo stop
            if hasattr(camera_object, 'started') and camera_object.started:
                self.logger.warning("Focus aid did not release the camera in time. Forcing stop.")
                try:
                    camera_object.stop()
                except Exception as e:
                    self.logger.error(f"Error while forcing camera stop: {e}")

            self.logger.info("Camera released. Restarting stream after pause...")
            day_period = self.components.day_period_calc.get_day_period()
            self._restart_stream_if_enabled(day_period)
            self.streaming_was_active = False
        
        self.capture_active.set()

    def apply_updated_config(self):
        """Applies the reloaded configuration to live components."""
        self.logger.info("Applying updated configuration to all components...")
        new_config = self.config_manager.decrypted_config
        self.components.update_camera_config(new_config)
        # Intervallo di scatto e pianificazione del timelapse vivono nel
        # pianificatore, non nei componenti: vanno ricostruiti a parte.
        if self.scheduler_manager:
            self.scheduler_manager.reload_jobs()
        self.netwatch.update_config(new_config.get("network", {}))
        mdns.publish(new_config, self.logger)

# --- Main Execution ---
class ClientIPFilter(logging.Filter):
    """Aggiunge a ogni record l'IP del client, se siamo dentro una richiesta Flask.

    Va agganciato agli handler e non al logger: i filtri di un logger non
    vedono i record che arrivano per propagazione dai logger figli.
    """

    def filter(self, record):
        try:
            record.client_ip = request.remote_addr if has_request_context() else "-"
        except Exception:
            record.client_ip = "-"
        return True

def setup_logging(log_level_str):
    """Configures the global logger for the application."""
    logger = logging.getLogger("zeroCam")
    log_level = getattr(logging, log_level_str.upper(), logging.INFO)
    logger.setLevel(log_level)
    formatter = logging.Formatter("%(asctime)s - %(threadName)s - %(levelname)s - [%(client_ip)s] - %(message)s")

    if not logger.handlers:
        # Console Handler
        console_handler = logging.StreamHandler()
        logger.addHandler(console_handler)

        # Rotating File Handler
        log_file_path = paths.LOG_FILE
        os.makedirs(paths.LOG_DIR, exist_ok=True)
        file_handler = logging.handlers.TimedRotatingFileHandler(log_file_path, when="D", interval=1, backupCount=7)
        file_handler.addFilter(ClientIPFilter())
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    return logger

def print_banner(logger):
    """Prints the application startup banner."""
    zerocam_banner = """
                                         /$$$$$$                                
                                        /$$__  $$                              
 /$$$$$$$$  /$$$$$$   /$$$$$$  /$$$$$$ | $$  \__/ /$$$$$$  /$$$$$$/$$$$ 
|____ /$$/ /$$__  $$ /$$__  $$/$$__  $$| $$      |____  $$| $$_  $$_  $$
   /$$$$/ | $$$$$$$$| $$  \__/ $$  \ $$| $$       /$$$$$$$| $$ \ $$ \ $$
  /$$__/  | $$_____/| $$      | $$  | $$| $$      /$$__  $$| $$ | $$ | $$
 /$$$$$$$$|  $$$$$$$| $$      |  $$$$$$/|  $$$$$$/  $$$$$$$| $$ | $$ | $$
|________/ \_______/|__/       \______/  \______/\_______/|__/ |__/ |__/
                                                  www.iz1kga.it - IZ1KGA
"""
    logger.info(zerocam_banner)
    logger.info(f"Version: {get_version()}")
    logger.info("This software is provided under a dual-license model:")
    logger.info("- Free for non-commercial use under the CC BY-NC-SA 4.0 license.")
    logger.info("- Commercial use requires a separate license. Please contact the author.")

def run_pre_start_checks(logger):
    """Performs critical checks before starting the main application."""
    device_id = os.getenv("DEVICE_ID")
    if not device_id:
        logger.critical("DEVICE_ID environment variable not set. Exiting.")
        exit(1)

    # La connessione si guarda, ma non si aspetta. Una webcam appena accesa
    # a casa di chi la usa non ha ancora una rete, ed è proprio quello il
    # momento in cui servono l'interfaccia web per dargliene una e l'hotspot
    # per raggiungerla: restando fermi qui il dispositivo non mostrerebbe
    # nulla, e l'unico modo per configurarlo sarebbe un terminale.
    if check_internet_connection():
        logger.info("Internet connection is available.")
    else:
        logger.warning("No internet connection: starting anyway, so that the web "
                       "interface and the fallback hotspot can be reached.")
    return device_id

if __name__ == "__main__":
    # Prima di tutto: configurazione e log vivono nella cartella dei dati, e
    # un'installazione aggiornata da una versione precedente li ha ancora in
    # quella dell'applicazione. Il logger non esiste ancora, perché il suo
    # file è fra le cose da spostare.
    migration_messages = paths.migrate_legacy_data()
    # Gli assets distribuiti con l'applicazione vanno versati fra i dati:
    # sono nuovi a ogni aggiornamento che ne aggiunge.
    asset_messages = paths.seed_bundled_assets()

    log_level = os.getenv("LOG_LEVEL", "INFO")
    main_logger = setup_logging(log_level)
    for message in migration_messages:
        main_logger.warning(message)
    for message in asset_messages:
        main_logger.info(message)

    print_banner(main_logger)
    
    device_id = run_pre_start_checks(main_logger)
    
    try:
        app = ZeroCamApp(device_id, main_logger)
        app.start()
        
        # Keep the main thread alive to handle signals like KeyboardInterrupt
        while not app.shutdown_flag.is_set():
            time.sleep(1)
            
    except KeyboardInterrupt:
        main_logger.info("Keyboard interrupt received. Initiating shutdown.")
        if 'app' in locals():
            app.shutdown()
    except Exception as e:
        main_logger.critical(f"A critical error occurred during initialization: {e}", exc_info=True)
        # The global exception handler will catch this, but we log it here for clarity.
        os._exit(1)