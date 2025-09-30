import os

from lib.helpers import (
    DayPeriodCalculator,
    ImageAnnotator,
    ImageCropper,
    PrivacyMasker,
    ImageOverlay,
    FTPUploader
)
from cameras import cameraFactory

class ComponentManager:
    """Initializes and holds all major application components."""

    def __init__(self, config_manager, logger):
        self.logger = logger
        self.config = config_manager.get
        self.day_period_calc = None
        self.camera = None
        self.annotator = None
        self.cropper = None
        self.overlay = None
        self.ftp_uploader = None
        self._initialize_all()

    def _initialize_all(self):
        """Sequentially initializes all components, with error handling."""
        self.logger.info("Initializing components...")
        self._init_day_period()
        self._init_camera()
        self._init_annotator()
        self._init_cropper()
        self._init_privacy_masker()
        self._init_overlay()
        self._init_ftp()
        self.logger.info("All components initialized successfully.")
    
    def _init_with_feedback(self, component_name, init_func):
        """Generic initializer with logging."""
        try:
            self.logger.info(f"Initializing {component_name}...")
            component = init_func()
            self.logger.info(f"{component_name} initialized.")
            return component
        except Exception as e:
            self.logger.critical(f"Fatal error initializing {component_name}: {e}. Shutting down.", exc_info=True)
            os._exit(1)

    def _init_day_period(self):
        def _init():
            dd = self.config("deviceDetails")
            return DayPeriodCalculator(
                dd["latitude"], dd["longitude"], dd["elevation"],
                dd.get("sunRiseOffset", 0), dd.get("sunSetOffset", 0),
                dd.get("duskOffset", 0), dd.get("dawnOffset", 0), self.logger
            )
        self.day_period_calc = self._init_with_feedback("DayPeriodCalculator", _init)

    def _init_camera(self):
        def _init():
            return cameraFactory(
                self.config("cameraParameters")["type"],
                self.config("cameraParameters"),
                self.config("streamParameters"),
                self.config("onvif", {}),
                self.config("deviceDetails"),
                self.logger,
            )
        self.camera = self._init_with_feedback("Camera", _init)
    
    def update_camera_config(self, new_config):
        if self.camera:
            self.logger.info("Passing new configuration to camera object...")
            self.camera.update_config(
                new_config.get('cameraParameters'),
                new_config.get('streamParameters'),
                new_config.get('deviceDetails')
            )
            self.cropper.update_config(new_config.get('cameraParameters', {}).get('crop', {}))
    
    def _init_annotator(self):
        def _init():
            return ImageAnnotator(self.config("Annotation"), self.logger)
        self.annotator = self._init_with_feedback("ImageAnnotator", _init)

    def _init_cropper(self):
        def _init():
            return ImageCropper(self.config("cameraParameters").get("crop", {}), self.logger)
        self.cropper = self._init_with_feedback("ImageCropper", _init)

    def _init_privacy_masker(self):
        def _init():
            return PrivacyMasker(logger=self.logger)
        self.privacy_masker = self._init_with_feedback("ImageCropper", _init)

    def _init_overlay(self):
        def _init():
            return ImageOverlay(self.config("OverlayImages"), self.logger)
        self.overlay = self._init_with_feedback("ImageOverlay", _init)

    def _init_ftp(self):
        def _init():
            return FTPUploader(self.config("FtpHost"), self.logger)
        self.ftp_uploader = self._init_with_feedback("FTPUploader", _init)