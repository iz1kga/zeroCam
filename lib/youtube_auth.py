# -*- coding: utf-8 -*-
"""
Autenticazione OAuth verso le API di YouTube.

Condivisa fra la gestione della diretta (lib/youtube_live.py) e l'upload
dei timelapse (lib/timelapse.py): stesse credenziali, stesso refresh
token, un solo punto in cui rinnovare l'access token.
"""

import threading
from datetime import datetime, timedelta, timezone

import requests

TOKEN_URL = "https://oauth2.googleapis.com/token"
API_BASE = "https://www.googleapis.com/youtube/v3"
UPLOAD_BASE = "https://www.googleapis.com/upload/youtube/v3"

# youtube: gestione dei broadcast. youtube.upload: caricamento dei video.
SCOPES = (
    "https://www.googleapis.com/auth/youtube "
    "https://www.googleapis.com/auth/youtube.upload"
)

REQUIRED_KEYS = ("client_id", "client_secret", "refresh_token")


class YouTubeAuth:
    """Custodisce le credenziali e fornisce un access token valido."""

    def __init__(self, config, logger):
        self.logger = logger
        self._lock = threading.Lock()
        self.cfg = {}
        self.timeout = 10
        self._access_token = None
        self._token_expiry = datetime.now(timezone.utc)
        self.update_config(config)

    def update_config(self, config):
        with self._lock:
            self.cfg = config or {}
            self.timeout = self.cfg.get("timeout", 10)
            self._access_token = None
            self._token_expiry = datetime.now(timezone.utc)

    @property
    def configured(self):
        return all(self.cfg.get(key) for key in REQUIRED_KEYS)

    def missing_keys(self):
        return [key for key in REQUIRED_KEYS if not self.cfg.get(key)]

    def token(self):
        """Access token valido, rinnovato quando serve."""
        now = datetime.now(timezone.utc)
        if self._access_token and now < self._token_expiry:
            return self._access_token

        self.logger.info("Refreshing YouTube OAuth access token...")
        r = requests.post(
            TOKEN_URL,
            data={
                "client_id": self.cfg["client_id"],
                "client_secret": self.cfg["client_secret"],
                "refresh_token": self.cfg["refresh_token"],
                "grant_type": "refresh_token",
            },
            timeout=self.timeout,
        )
        if r.status_code != 200:
            raise RuntimeError(f"OAuth refresh failed ({r.status_code}): {r.text}")

        payload = r.json()
        self._access_token = payload["access_token"]
        # 60s di margine per non usare un token che scade durante la chiamata
        self._token_expiry = now + timedelta(seconds=int(payload.get("expires_in", 3600)) - 60)
        return self._access_token

    def headers(self, extra=None):
        headers = {"Authorization": f"Bearer {self.token()}"}
        if extra:
            headers.update(extra)
        return headers

    def api(self, method, path, params=None, body=None):
        """Chiamata all'API v3, con errore parlante sui codici >= 400."""
        r = requests.request(
            method,
            f"{API_BASE}/{path}",
            headers=self.headers(),
            params=params,
            json=body,
            timeout=self.timeout,
        )
        if r.status_code >= 400:
            raise RuntimeError(f"YouTube API {method} {path} failed ({r.status_code}): {r.text}")
        return r.json() if r.content else {}
