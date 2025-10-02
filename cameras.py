#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
sys.excepthook = sys.__excepthook__

import time
import os
from PIL import Image, ImageDraw, ImageFont, ImageStat
import io
from io import BytesIO
from fractions import Fraction
from lib.helpers import logRecursive
import random
import threading
import subprocess
import select
import cv2
import numpy as np
import importlib.metadata
from libcamera import Transform
import copy
import json


def cameraFactory(camera_type, *args, **kwargs):
    if camera_type == 'fakeCamera':
        return fakeCameraDevice(*args, **kwargs)
    elif camera_type == 'piCamera':
        return PiCameraDevice(*args, **kwargs)
    else:
        raise ValueError(f"Unknown camera type: {camera_type}")

class fakeCameraDevice:
    def __init__(self, params, streamParams, onvifParams, deviceParams, logger):
        self.logger = logger
        self.params = params
        self.streamParams = streamParams
        self.onvifParams = onvifParams
        self.logger.info("Camera Object Created")
        logRecursive(self.logger, self.params)

    def update_config(self, new_params, new_stream_params, new_device_params):
        self.logger.info("Updating camera configuration with new settings...")
        self.params = new_params
        self.streamParams = new_stream_params
        self.deviceParams = new_device_params

    def fakeImage(self):
        width = 4000
        height = 3000
        text = "This is a test image"
        # Create a blank image with a background color
        color = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
        image = Image.new("RGB", (width, height), color)
        return image

    def takePicture(self, dayperiod):
        self.logger.info(f"Starting capture - {dayperiod}")
        image = self.fakeImage()
        # Save the image to a byte buffer
        image_buffer = BytesIO()
        image.save(image_buffer, format='JPEG')
        image_buffer.seek(0)
        return image_buffer, {}
    
    def streamStart(self, dayperiod):
        self.logger.info("Fake streaming started.")

    def streamStop(self):
        self.logger.info("Fake streaming stopped.")

    def get_image(self):
        self.logger.info("Getting fake image.")
        return self.takePicture('day')

class PiCameraDevice:
    def __init__(self, params, streamParams, onvifParams, deviceParams, logger):
        self.logger = logger
        self.params = params
        self.streamParams = streamParams
        self.onvifParams = onvifParams
        self.deviceParams = deviceParams
        self.last_known_exposure_index = None
        self.capture_info = None
        self.logger.info("Camera Object Created")
        self._init_capture_index()
        logRecursive(self.logger, self.params)
        from picamera2 import Picamera2
        try:
            version = importlib.metadata.version('picamera2')
            self.logger.info(f"Using picamera2 version: {version}")
        except importlib.metadata.PackageNotFoundError:
            self.logger.warning("Could not determine picamera2 version.")
        self.camera = Picamera2()
        self.running = False
        # Define and create the shared memory directory for stream frames
        self.shmem_path = '/usr/local/zerocam/app/shmem'
        os.makedirs(self.shmem_path, exist_ok=True)
        self.logger.info(f"Shared memory path for stream frames set to: {self.shmem_path}")

    def _init_capture_index(self):
        with open('.capture_info', 'r') as f:
            self.capture_info = json.load(f)
            self.last_known_exposure_index = self.capture_info.get('capture_idx', 0)

    def _store_capture_index(self):
        with open('.capture_info', 'w') as f:
            self.capture_info['capture_idx'] = self.last_known_exposure_index
            json.dump(self.capture_info, f)
            self.logger.info(f"Stored capture index: {self.last_known_exposure_index}")

    def update_config(self, new_params, new_stream_params, new_device_params):
        self.logger.info("Updating camera configuration with new settings...")
        self.params = new_params
        self.streamParams = new_stream_params
        self.deviceParams = new_device_params

    def get_image(self ):
        output_buffer = BytesIO()
        self.logger.debug("Getting Image")
        self.camera.capture_file(output_buffer, format="jpeg")
        metadata = self.camera.capture_metadata()
        self.logger.debug(metadata)
        return output_buffer, metadata

    
    

    def takePicture(self, dayperiod):
        """
        Cattura un'immagine usando l'esposizione automatica per il giorno ('day')
        o un bracketing manuale per le altre fasi (dawn, dusk, night).
        """
        
        self.logger.info(f"--- Inizio cattura per '{dayperiod}' ---")
        params = copy.deepcopy(self.params.get(dayperiod, {}))
        SHUTTER_SPEEDS_SECONDS = [1/8, 1/4, 1/2, 3/4, 1, 2, 4, 6, 8, 10, 12, 15, 20, 30, 45, 60]
        BRIGHTNESS_TARGET_MIN = params.get("MinTargetBrightness", 40)
        BRIGHTNESS_TARGET_MAX = params.get("MaxTargetBrightness", 55)
        try:
            # Configurazione comune a entrambi i metodi di scatto
            transform = Transform(hflip=self.deviceParams.get("hflip", False), vflip=self.deviceParams.get("vflip", False))
            config = self.camera.create_still_configuration(transform=transform, buffer_count=3, queue=False)
            self.camera.configure(config)

            # --- BIVIO LOGICO: Giorno vs. Altre Fasi ---
            if dayperiod == "day":
                # --- LOGICA PER LO SCATTO DIURNO (dayperiod == 'day') ---
                self.logger.info("Modalità diurna: uso l'esposizione automatica della camera (AeEnable=True).")

                day_params = {
                "AeEnable": True,
                "AwbEnable": True,
                "AwbMode": params.get("AwbMode", 0),
                "AeMeteringMode": params.get("AeMeteringMode", 0), 
                "AnalogueGain": 1.0,
                "ExposureTime": 0,
                "ExposureValue": 0,
                "HdrMode": params.get("HdrMode", 2),
                "NoiseReductionMode": params.get("NoiseReductionMode", 1),
                "Sharpness": params.get("Sharpness", 4)
                }
                
                self.camera.set_controls(day_params)
                self.camera.start()
                self.logger.info("In attesa della stabilizzazione dell'esposizione automatica (2 secondi)...")
                time.sleep(2)

                output_buffer = io.BytesIO()
                self.camera.capture_file(output_buffer, format="jpeg")
                metadata = self.camera.capture_metadata()
                self.logger.info(
                    f"Cattura diurna completata. Gain: {metadata.get('AnalogueGain'):.2f}, "
                    f"Esposizione: {metadata.get('ExposureTime')/1000000:.4f}s"
                )
                return output_buffer, metadata

            else:
                # --- LOGICA PER SCATTI NOTTURNI/CREPUSCOLO (bracketing) ---
                # Questa è la tua logica esistente, ora nel ramo 'else'.
                self.logger.info("Modalità crepuscolo/notte: uso il bracketing manuale dell'esposizione.")
                shutter_speeds_us = [int(s * 1_000_000) for s in SHUTTER_SPEEDS_SECONDS]
                
                if hasattr(self, 'last_known_exposure_index') and self.last_known_exposure_index is not None:
                    shutter_idx = self.last_known_exposure_index
                else:
                    shutter_idx = 8 
                
                manual_controls = {
                    "AeEnable": False, 
                    "AwbEnable": True, 
                    "AnalogueGain": 1.0,
                    "FrameDurationLimits": (100, 100_000_000),
                }
                self.camera.set_controls(manual_controls)
                
                exp_results = {}
                max_attempts = 30
                
                for attempt in range(max_attempts):
                    if not (0 <= shutter_idx < len(shutter_speeds_us)):
                        self.logger.warning("Indice di scatto fuori dai limiti. Interrompo la ricerca.")
                        break

                    # --- ANTI-BOUNCING ---
                    if shutter_idx in exp_results:
                        self.logger.warning(f"Rilevata oscillazione! L'indice {shutter_idx} è già stato testato. Interrompo la ricerca per scegliere il migliore.")
                        break

                    exposure_us = shutter_speeds_us[shutter_idx]
                    
                    self.logger.info(f"Tentativo {attempt + 1}/{max_attempts}: Indice={shutter_idx}, Esposizione={exposure_us/1_000_000:.4f}s")
                    self.camera.set_controls({"ExposureTime": exposure_us})
                    
                    self.camera.start()
                    # sensor warmup time
                    time.sleep(2)
                    
                    current_buffer = io.BytesIO()
                    self.camera.capture_file(current_buffer, format="jpeg")
                    metadata = self.camera.capture_metadata()
                    self.camera.stop()

                    if not current_buffer.getbuffer().nbytes:
                        self.logger.error("Buffer immagine vuoto, salto.")
                        continue

                    current_buffer.seek(0)
                    with Image.open(current_buffer) as img:
                        brightness = ImageStat.Stat(img.convert('L')).mean[0]

                    self.logger.info(f"Esposizione={exposure_us/1_000_000:.4f}s, Luminosità={brightness:.2f}")
                    
                    exp_results[shutter_idx] = {"brightness": brightness, "metadata": metadata, "image": current_buffer}

                    if BRIGHTNESS_TARGET_MIN <= brightness <= BRIGHTNESS_TARGET_MAX:
                        self.logger.info(f"Esposizione ottimale trovata! Salvo l'indice {shutter_idx}.")
                        self.last_known_exposure_index = shutter_idx
                        self._store_capture_index()
                        return current_buffer, metadata
                    
                    elif brightness < BRIGHTNESS_TARGET_MIN:
                        shutter_idx += 1 
                    elif brightness > BRIGHTNESS_TARGET_MAX:
                        shutter_idx -= 1

                # ... (logica di fallback per scegliere il migliore, invariata)
                self.logger.warning("Nessuna esposizione perfetta trovata. Scelgo la più vicina.")
                if not exp_results: return None, {}
                target_br = (BRIGHTNESS_TARGET_MIN + BRIGHTNESS_TARGET_MAX) / 2
                best_idx = min(exp_results.keys(), key=lambda idx: abs(exp_results[idx]['brightness'] - target_br))
                best_result = exp_results[best_idx]
                self.logger.info(f"Scatto migliore: Indice={best_idx}, Luminosità={best_result['brightness']:.2f}")
                self.last_known_exposure_index = best_idx
                self._store_capture_index()           
                return best_result['image'], best_result['metadata']

        except Exception as e:
            self.logger.error(f"Errore durante takePicture: {e}", exc_info=True)
            if self.camera.started:
                self.camera.stop()
            return None, {}
        finally:
            # Il blocco finally viene eseguito sempre, garantendo che la camera venga fermata
            if self.camera.started:
                self.camera.stop()
                time.sleep(2)
                self.logger.info("--- Fine cattura, camera fermata. ---")
                time.sleep(2)

    def takePicture_old(self, dayperiod):
        """
        Cattura un'immagine, con l'opzione di lasciare la camera in esecuzione.
        """
        self.logger.info(f"--- Inizio cattura per '{dayperiod}' ---")
        output_buffer = BytesIO()
        
        try:
            # 1. Prepara i parametri e i controlli
            params = copy.deepcopy(self.params.get(dayperiod, {}))
            is_auto_mode = params.get("AeEnable", True)

            # Prepara la configurazione base della camera
            transform = Transform(hflip=self.deviceParams.get("hflip", False), vflip=self.deviceParams.get("vflip", False))
            config = self.camera.create_still_configuration(transform=transform)
            self.camera.configure(config)

            params['AwbEnable'] = True
            params['AeExposureMode'] = 2 # prefer long exposure
            self.camera.set_controls(params)

            self.camera.start()
            self.logger.info("In attesa della stabilizzazione del sensore (2 secondi)...")
            time.sleep(2)

            self.logger.info(f"Cattura dell'immagine {params['ExposureTime']/1000000:.2f}s a Gain {params.get('AnalogueGain')}")
            self.camera.capture_file(output_buffer, format="jpeg")
            metadata = self.camera.capture_metadata()
            self.logger.info(f"Cattura completata. Gain: {metadata.get('AnalogueGain'):.2f}, Esposizione: {metadata.get('ExposureTime')/1000000:.2f}")

            return output_buffer, metadata

        except Exception as e:
            self.logger.error(f"Errore durante takePicture per '{dayperiod}': {e}", exc_info=True)
            if self.camera.started:
                    self.camera.stop()
            return None, {}
        finally:
            if self.camera.started:
                self.camera.stop()
                self.logger.info("--- Fine cattura, camera fermata. ---")


    def streamStart(self, dayperiod):
        if self.running:
            self.logger.warning("Stream is already running. Please stop it first.")
            return
        self.logger.info("Starting video streaming thread")
        self.streamThread = threading.Thread(target=self.streamNow, args=(dayperiod,), daemon=True, name="YouTubeStreamThread")
        self.streamThread.start()

    def streamNow(self, dayperiod):
        # --- 1. CONTROLLO ABILITAZIONE STREAM ---
        # Controlla se gli stream sono abilitati nella configurazione.
        # Il metodo .get() ritorna False se la chiave non è presente.
        dayperiod_params = copy.deepcopy(self.streamParams.get(dayperiod, {}))
        yt_enabled = self.streamParams.get("enabled", False)
        onvif_enabled = self.onvifParams.get("enabled", False)
        
        self.logger.info(f"Stream status: YouTube={'ENABLED' if yt_enabled else 'DISABLED'}, ONVIF={'ENABLED' if onvif_enabled else 'DISABLED'}")

        # Se nessuno stream è abilitato, esci subito.
        if not yt_enabled and not onvif_enabled:
            self.logger.warning("Both YouTube and ONVIF streams are disabled. Exiting.")
            self.running = False # Assicura che lo stato sia consistente
            return

        # --- 2. CONFIGURAZIONE CAMERA (COMUNE A ENTRAMBI) ---
        # Questa configurazione è necessaria se almeno uno stream è attivo.
        fr = dayperiod_params.pop("framerate", 10)
        w, h = self.streamParams["width"], self.streamParams["height"]
        onvif_w = self.onvifParams.get("onvif_w", 1920)
        onvif_h = int(onvif_w * (h / w))
        
        hflip = self.deviceParams.get("hflip", False)
        vflip = self.deviceParams.get("vflip", False)
        transform = Transform(hflip=hflip, vflip=vflip)

        video_config = self.camera.create_video_configuration(
            main={"size": (w, h), "format": "YUV420"},
            lores={"size": (onvif_w, onvif_h), "format": "RGB888"},
            controls={"FrameRate": fr, "HdrMode": 0},
            transform=transform
        )
        self.camera.configure(video_config)
        dayperiod_params["AeEnable"] = True
        dayperiod_params["AwbEnable"] = True
        self.logger.info(f"dayperiod_params: {dayperiod_params}")
        self.camera.set_controls(dayperiod_params)
        self.camera.start()
        time.sleep(2)

        # --- 3. INIZIALIZZAZIONE CONDIZIONALE ---
        self.ffmpeg_proc = None
        output_image_path = None

        if yt_enabled:
            api_key = self.streamParams["yt_api_key"]
            bitrate = self.streamParams.get("bitrate", "4500k")
            bufsize = self.streamParams.get("bufsize", "9000k")
            
            ffmpeg_cmd = [
                "ffmpeg", "-f", "rawvideo", "-pix_fmt", "yuv420p", "-s", f"{w}x{h}", "-r", str(fr), "-i", "-",
                "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
                "-c:v", "libx264", "-preset", "veryfast", "-b:v", bitrate, "-maxrate", bitrate, "-bufsize", bufsize,
                "-g", str(int(fr * 2)),
                "-c:a", "aac", "-ar", "44100", "-b:a", "128k",
                "-f", "flv", f"rtmp://a.rtmp.youtube.com/live2/{api_key}"
            ]
            
            self.logger.info("Starting ffmpeg process for YouTube stream...")
            self.ffmpeg_proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE)

        if onvif_enabled:
            # Assicura che la directory esista
            os.makedirs(self.shmem_path, exist_ok=True)
            output_image_path = os.path.join(self.shmem_path, 'stream_latest.jpg')
            self.logger.info(f"ONVIF frame saving enabled. Path: {output_image_path}")

        # --- 4. LOOP PRINCIPALE DELLO STREAMING ---
        self.running = True
        last_frame_save_time = 0

        while self.running:
            request = None
            try:
                request = self.camera.capture_request()

                # --- Gestione Stream YouTube ---
                if yt_enabled and self.ffmpeg_proc and self.ffmpeg_proc.stdin:
                    main_frame = request.make_array("main")
                    if select.select([], [self.ffmpeg_proc.stdin], [], 0)[1]:
                        try:
                            self.ffmpeg_proc.stdin.write(main_frame.tobytes())
                            self.ffmpeg_proc.stdin.flush()
                        except (BrokenPipeError, OSError):
                            self.logger.error("Broken pipe with ffmpeg, stopping stream.")
                            break # Esce dal loop se ffmpeg si chiude inaspettatamente
                    else:
                        self.logger.warning("Frame skipped for YouTube (ffmpeg busy)")
                
                # --- Gestione Stream ONVIF (salvataggio frame) ---
                if onvif_enabled:
                    current_time = time.time()
                    if current_time - last_frame_save_time >= 1.0: # Salva al massimo un frame al secondo
                        lores_frame = request.make_array("lores")
                        try:
                            rgb_frame = cv2.cvtColor(lores_frame, cv2.COLOR_BGR2RGB)
                            img = Image.fromarray(rgb_frame, 'RGB')
                            img.save(output_image_path, 'JPEG', quality=85)
                            last_frame_save_time = current_time
                            self.logger.debug(f"Saved ONVIF frame to {output_image_path}")
                        except Exception as e:
                            self.logger.error(f"Failed to save ONVIF stream frame: {e}")

            except Exception as e:
                self.logger.error(f"Streaming Error: {e}", exc_info=True)
                break
            finally:
                if request:
                    request.release()
        self.logger.info("Streaming loop requested to stop. Cleaning up resources...")
        
        if yt_enabled and hasattr(self, 'ffmpeg_proc') and self.ffmpeg_proc and self.ffmpeg_proc.poll() is None:
            self.logger.info("Attempting graceful shutdown of ffmpeg process...")
            try:
                if self.ffmpeg_proc.stdin:
                    self.ffmpeg_proc.stdin.close()
                self.ffmpeg_proc.wait(timeout=2)
                self.logger.info("ffmpeg process exited gracefully.")
            except subprocess.TimeoutExpired:
                self.logger.warning("ffmpeg did not exit gracefully. Terminating...")
                self.ffmpeg_proc.terminate()
                try:
                    self.ffmpeg_proc.wait(timeout=2)
                    self.logger.info("ffmpeg process terminated successfully.")
                except subprocess.TimeoutExpired:
                    self.logger.error("ffmpeg did not terminate. Killing process...")
                    self.ffmpeg_proc.kill()
                    self.logger.info("ffmpeg process killed.")
            except (BrokenPipeError, OSError) as e:
                self.logger.error(f"Error while closing ffmpeg stdin: {e}. Terminating process.")
                self.ffmpeg_proc.terminate()
                time.sleep(1)
                if self.ffmpeg_proc.poll() is None:
                    self.ffmpeg_proc.kill()
        
        self.logger.info("Cleanup complete. Exiting streaming thread.")

    def streamStop(self):
        if not self.running:
            self.logger.info("Stream is not running.")
            return
            
        self.logger.info("Stopping video streaming...")
        self.running = False # This flag will cause the streamNow loop to exit

        if hasattr(self, "streamThread") and self.streamThread.is_alive():
            self.logger.info("Waiting for streaming thread to finish cleanup...")
            # REMOVED TIMEOUT: This will now block until the thread is actually finished.
            self.streamThread.join()
            self.logger.info("Streaming thread has finished.")

        if self.camera.started:
            self.logger.info("Stopping camera...")
            self.camera.stop()

        self.logger.info("✅ Streaming stopped correctly.")


if __name__ == '__main__':
    print("Devices Classes")

