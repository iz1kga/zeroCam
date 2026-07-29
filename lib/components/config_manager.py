import os
import json
import threading

from lib import paths
from lib.helpers import CryptoHelper

# Sezioni introdotte dopo il rilascio iniziale: se mancano dal file di
# configurazione vengono inserite con questi valori, così le installazioni
# esistenti continuano a partire e mostrano la pagina nell'interfaccia web.
DEFAULT_SECTIONS = {
    "settingsManager": {
        "port": 8080,
        "http_enabled": True,
        "https_enabled": False,
        "https_port": 8443,
        "https_hostnames": [],
        "public_page": False,
        "public_title": "",
        "public_live_url": "",
    },
    # L'upload FTP esisteva prima di avere un interruttore: chi ce l'ha
    # configurato lo vuole acceso, quindi il default lo lascia com'era.
    "FtpHost": {
        "enabled": True,
    },
    "streamParameters": {
        "extra_destinations": [],
        "overlay": False,
        "audio_file": "",
        "audio_volume": 100,
    },
    "youtubeLive": {
        "enabled": False,
        "client_id": "",
        "client_secret": "",
        "refresh_token": "",
        "title": "Live {date}",
        "description": "",
        "privacy": "public",
        "latency": "low",
        "dvr": True,
        "record": True,
        "made_for_kids": False,
        "end_on_shutdown": False,
        "daily_reset_time": "",
        "timeout": 10,
    },
    "timelapse": {
        "enabled": False,
        "day": "monday",
        "time": "03:00",
        "fps": 25,
        "frame_width": 2560,
        "frame_quality": 88,
        "crf": 20,
        "preset": "medium",
        "threads": 2,
        "nice": 19,
        "min_frames": 30,
        "retention_weeks": 4,
        "audio_file": "",
        "audio_volume": 100,
        "keep_local": True,
        "frames_dir": "./timelapse_frames",
        "output_dir": "./timelapse",
        "title": "Timelapse {from} - {to}",
        "description": "",
        "privacy": "public",
        "made_for_kids": False,
    }
}

class ConfigManager:
    """Handles loading, saving, and decrypting application configuration."""

    def __init__(self, logger, secret_key, config_path=None):
        self.logger = logger
        self.config_path = config_path or paths.CONFIG_FILE
        self.config_lock = threading.RLock()
        self.crypto_helper = CryptoHelper(secret_key, self.logger)
        self.config = {}
        self.decrypted_config = {}
        self.load_config()

    def load_config(self):
        """Loads and decrypts the configuration from the JSON file."""
        self.logger.info(f"Loading configuration from {self.config_path}")
        if not os.path.exists(self.config_path):
            self.logger.critical(f"Configuration file not found at {self.config_path}. Shutting down.")
            os._exit(1)

        try:
            with self.config_lock:
                with open(self.config_path, "r") as f:
                    self.config = json.load(f)

                self._apply_default_sections()

                # Create a deep copy for decryption
                self.decrypted_config = json.loads(json.dumps(self.config))

                # Decrypt sensitive fields
                self._decrypt_field(['mqtt', 'password'])
                self._decrypt_field(['FtpHost', 'password'])
                self._decrypt_field(['onvif', 'password'])
                self._decrypt_field(['streamParameters', 'yt_api_key'])
                self._decrypt_field(['youtubeLive', 'client_secret'])
                self._decrypt_field(['youtubeLive', 'refresh_token'])
                self._decrypt_field(['HttpUploader', 'token'])

        except (json.JSONDecodeError, IOError) as e:
            self.logger.critical(f"Failed to load or parse configuration: {e}. Shutting down.", exc_info=True)
            os._exit(1)

    def _apply_default_sections(self):
        """Aggiunge le sezioni (e le chiavi) mancanti dopo un aggiornamento."""
        for section, defaults in DEFAULT_SECTIONS.items():
            current = self.config.setdefault(section, {})
            if not isinstance(current, dict):
                continue
            for key, value in defaults.items():
                current.setdefault(key, value)

    def _decrypt_field(self, path):
        """Helper to decrypt a nested configuration value."""
        try:
            temp = self.decrypted_config
            for key in path[:-1]:
                temp = temp[key]
            
            field = path[-1]
            if field in temp and isinstance(temp[field], str):
                temp[field] = self.crypto_helper.decrypt(temp[field])
        except (KeyError, TypeError):
            # Field does not exist, which is fine.
            pass

    def save_config(self, new_config):
        """Encrypts sensitive fields and saves the configuration to a file."""
        self.logger.info("Saving new configuration...")
        with self.config_lock:
            try:
                # Create a deep copy to avoid modifying the live config object
                config_to_save = json.loads(json.dumps(new_config))

                # Encrypt sensitive fields if they are not already encrypted
                self._encrypt_field(config_to_save, ['FtpHost', 'password'])
                self._encrypt_field(config_to_save, ['mqtt', 'password'])
                self._encrypt_field(config_to_save, ['onvif', 'password'])
                self._encrypt_field(config_to_save, ['streamParameters', 'yt_api_key'])
                self._encrypt_field(config_to_save, ['youtubeLive', 'client_secret'])
                self._encrypt_field(config_to_save, ['youtubeLive', 'refresh_token'])
                self._encrypt_field(config_to_save, ['HttpUploader', 'token'])
                
                with open(self.config_path, 'w') as f:
                    json.dump(config_to_save, f, indent=2)
                
                self.logger.info("Configuration saved successfully. Reloading...")
                self.load_config() # Reload to apply changes
                return True
            except Exception as e:
                self.logger.error(f"Failed to save configuration: {e}", exc_info=True)
                return False

    def _encrypt_field(self, config, path):
        """Helper to encrypt a nested configuration value."""
        try:
            temp = config
            for key in path[:-1]:
                temp = temp[key]

            field = path[-1]
            if field in temp and temp[field] and not str(temp[field]).startswith("enc:"):
                temp[field] = self.crypto_helper.encrypt(temp[field])
        except (KeyError, TypeError):
            pass # Field does not exist

    def get(self, key, default=None):
        """Gets a decrypted configuration value."""
        return self.decrypted_config.get(key, default)

    def get_raw(self, key, default=None):
        """Gets a raw (not decrypted) configuration value."""
        return self.config.get(key, default)