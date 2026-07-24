import time
import threading
import schedule

class SchedulerManager:
    """Manages all scheduled jobs for the application."""

    def __init__(self, app, logger):
        self.app = app
        self.logger = logger
        self.shutdown_flag = app.shutdown_flag
        self.capture_active_flag = app.capture_active
        self.scheduler_thread = None

    def setup_jobs(self):
        """Sets up all recurring jobs based on configuration."""
        self.logger.info("Setting up scheduled jobs...")
        
        # Capture Job
        interval = int(self.app.config_manager.get("cameraParameters", {}).get("shotInterval", 300))
        schedule.every(interval).seconds.do(self._safe_capture_job)
        self.logger.info(f"Capture job scheduled every {interval} seconds.")
        
        # Diagnostic Job
        schedule.every(60).seconds.do(self.app.publish_diagnostic)
        self.logger.info("Diagnostic job scheduled every 60 seconds.")
        
        # Stats Collector Job
        schedule.every(1).seconds.do(self.app.stats_collector.collect_and_process)
        self.logger.info("Stats collection job scheduled every 1 second.")

        self._setup_timelapse_job()

    def _setup_timelapse_job(self):
        """Schedules the weekly timelapse build plus the daily frame cleanup."""
        timelapse_config = self.app.config_manager.get("timelapse", {})
        if not timelapse_config.get("enabled", False):
            self.logger.info("Timelapse is disabled, no job scheduled.")
            return

        day = str(timelapse_config.get("day", "monday")).lower()
        at_time = str(timelapse_config.get("time", "03:00"))

        weekday = getattr(schedule.every(), day, None)
        if weekday is None:
            self.logger.error(f"Invalid timelapse day '{day}', falling back to monday.")
            weekday = schedule.every().monday

        weekday.at(at_time).do(self._safe_timelapse_job)
        self.logger.info(f"Timelapse job scheduled every {day} at {at_time}.")

        # La pulizia gira comunque ogni giorno: se il montaggio fallisce per
        # settimane, i fotogrammi non devono accumularsi senza limite.
        schedule.every().day.at("04:30").do(self.app.components.timelapse.cleanup_old_frames)
        self.logger.info("Timelapse frame cleanup scheduled daily at 04:30.")

    def _safe_timelapse_job(self):
        """Runs the timelapse build without ever taking down the scheduler."""
        try:
            self.app.publish_diagnostic("Building timelapse")
            self.app.components.timelapse.run()
        except Exception:
            self.logger.error("Timelapse job crashed.", exc_info=True)
        finally:
            self.app.publish_diagnostic("Idle")

    def _run_scheduler(self):
        """The main loop for the scheduler thread."""
        self.logger.info("Scheduler thread started.")
        while not self.shutdown_flag.is_set():
            self.capture_active_flag.wait() # Pauses here if capture is inactive
            schedule.run_pending()
            time.sleep(1)
        self.logger.info("Scheduler thread stopped.")

    def _safe_capture_job(self):
        """Wrapper to catch exceptions within the scheduled capture job."""
        try:
            self.app.capture_job()
        except Exception:
            self.logger.critical("Capture job crashed! Initiating shutdown.", exc_info=True)
            self.app.publish_diagnostic("Error: Capture Job CRASHED")
            self.app.shutdown()

    def start(self):
        """Starts the scheduler in a separate thread."""
        self.setup_jobs()
        # Trigger an immediate capture on startup
        first_capture_thread = threading.Thread(target=self._safe_capture_job, name="FirstCaptureThread", daemon=True)
        first_capture_thread.start()
        
        self.scheduler_thread = threading.Thread(target=self._run_scheduler, name="SchedulerThread", daemon=True)
        self.scheduler_thread.start()
        return self.scheduler_thread