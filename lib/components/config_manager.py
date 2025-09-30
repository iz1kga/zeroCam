import os
import json
import threading

from lib.helpers import CryptoHelper

class ConfigManager:
    """Handles loading, saving, and decrypting application configuration."""

    def __init__(self, logger, secret_key, config_path='.conf.json'):
        self.logger = logger
        self.config_path = config_path
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
                
                # Create a deep copy for decryption
                self.decrypted_config = json.loads(json.dumps(self.config))

                # Decrypt sensitive fields
                self._decrypt_field(['mqtt', 'password'])
                self._decrypt_field(['FtpHost', 'password'])
                self._decrypt_field(['streamParameters', 'yt_api_key'])

        except (json.JSONDecodeError, IOError) as e:
            self.logger.critical(f"Failed to load or parse configuration: {e}. Shutting down.", exc_info=True)
            os._exit(1)

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
                self._encrypt_field(config_to_save, ['streamParameters', 'yt_api_key'])
                
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