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
DEVICE_CODE_URL = "https://oauth2.googleapis.com/device/code"
DEVICE_GRANT_TYPE = "urn:ietf:params:oauth:grant-type:device_code"
API_BASE = "https://www.googleapis.com/youtube/v3"
UPLOAD_BASE = "https://www.googleapis.com/upload/youtube/v3"

# youtube: gestione dei broadcast. youtube.upload: caricamento dei video.
SCOPES = (
    "https://www.googleapis.com/auth/youtube "
    "https://www.googleapis.com/auth/youtube.upload"
)

# Il device flow ammette solo un sottoinsieme di scope: youtube.upload non è
# tra questi. Ma videos.insert accetta anche lo scope 'youtube', che il device
# flow concede, quindi con il solo 'youtube' si coprono sia le dirette sia
# l'upload dei timelapse.
DEVICE_SCOPE = "https://www.googleapis.com/auth/youtube"

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


class YouTubeDeviceFlow:
    """
    OAuth "device flow" per ottenere il refresh token dall'interfaccia web.

    Pensato per un dispositivo headless raggiunto via LAN: non serve un
    redirect, né HTTPS, né un browser sul Pi. L'utente inserisce le
    credenziali del proprio client OAuth, preme un pulsante e autorizza da
    un altro dispositivo digitando un codice breve. Il Pi attende e riceve
    il refresh token.

    Richiede un client OAuth di tipo "TV e dispositivi di immissione
    limitata": lo stesso motivo per cui basta lo scope 'youtube'.
    """

    def __init__(self, logger):
        self.logger = logger
        self.timeout = 15
        self._lock = threading.Lock()
        self._pending = None  # device_code, client_id, client_secret, interval

    def start(self, client_id, client_secret):
        """
        Avvia il flusso e ritorna il codice da mostrare all'utente.

        Solleva ValueError se mancano le credenziali, RuntimeError se Google
        rifiuta la richiesta (tipicamente client del tipo sbagliato).
        """
        if not client_id or not client_secret:
            raise ValueError("Client ID e Client Secret sono obbligatori.")

        r = requests.post(
            DEVICE_CODE_URL,
            data={"client_id": client_id, "scope": DEVICE_SCOPE},
            timeout=self.timeout,
        )
        if r.status_code != 200:
            raise RuntimeError(self._explain(r))

        data = r.json()
        with self._lock:
            self._pending = {
                "device_code": data["device_code"],
                "client_id": client_id,
                "client_secret": client_secret,
                "interval": int(data.get("interval", 5)),
            }
        self.logger.info("YouTube device flow started, waiting for user authorization.")
        return {
            "user_code": data["user_code"],
            # Google usa 'verification_url'; lo standard 'verification_uri'
            "verification_url": data.get("verification_url") or data.get("verification_uri"),
            "expires_in": int(data.get("expires_in", 1800)),
            "interval": int(data.get("interval", 5)),
        }

    def poll(self):
        """
        Interroga Google una volta. Ritorna lo stato del flusso.

        status: 'idle' (nessun flusso), 'pending' (in attesa),
        'authorized' (con refresh_token), 'failed' (con error).
        """
        with self._lock:
            pending = dict(self._pending) if self._pending else None
        if not pending:
            return {"status": "idle"}

        r = requests.post(
            TOKEN_URL,
            data={
                "client_id": pending["client_id"],
                "client_secret": pending["client_secret"],
                "device_code": pending["device_code"],
                "grant_type": DEVICE_GRANT_TYPE,
            },
            timeout=self.timeout,
        )

        if r.status_code == 200:
            payload = r.json()
            refresh = payload.get("refresh_token")
            self._clear()
            if not refresh:
                return {"status": "failed", "error": "nessun refresh token restituito"}
            channel = self._channel_title(payload.get("access_token"))
            self.logger.info(
                f"YouTube device flow authorized, refresh token obtained for channel '{channel or '?'}'."
            )
            return {"status": "authorized", "refresh_token": refresh, "channel": channel}

        error = ""
        try:
            error = r.json().get("error", "")
        except ValueError:
            error = r.text

        # In attesa che l'utente completi: non è un errore.
        if error in ("authorization_pending", "slow_down"):
            return {"status": "pending"}

        self._clear()
        self.logger.warning(f"YouTube device flow ended: {error}")
        return {"status": "failed", "error": error or "autorizzazione non riuscita"}

    def _channel_title(self, access_token):
        """
        Nome del canale appena autorizzato, per mostrarlo a chi autentica.

        Sbagliare account è l'errore piu' facile del device flow: la stream
        key sta su un canale e il token su un altro, e ce ne si accorge solo
        allo scatto successivo con un 403. Costa un'unita' di quota.
        """
        if not access_token:
            return ""
        try:
            r = requests.get(
                f"{API_BASE}/channels",
                headers={"Authorization": f"Bearer {access_token}"},
                params={"part": "snippet", "mine": "true"},
                timeout=self.timeout,
            )
            if r.status_code != 200:
                return ""
            items = r.json().get("items", [])
            return items[0].get("snippet", {}).get("title", "") if items else ""
        except requests.exceptions.RequestException:
            return ""

    def cancel(self):
        self._clear()

    def _clear(self):
        with self._lock:
            self._pending = None

    @staticmethod
    def _explain(response):
        try:
            error = response.json().get("error", "")
        except ValueError:
            error = response.text
        if error in ("invalid_client", "unauthorized_client"):
            return ("Credenziali non valide o client OAuth del tipo sbagliato. "
                    "Serve un client di tipo 'TV e dispositivi di immissione limitata'.")
        return f"Avvio del flusso non riuscito ({response.status_code}): {error or response.text}"
