# -*- coding: utf-8 -*-
"""
Gestione del ciclo di vita della diretta YouTube (Data API v3).

Il push RTMP fatto da cameras.py alimenta solo l'oggetto *liveStream*
(la chiave di streaming). Per essere realmente in onda serve un
*liveBroadcast* legato a quello stream: senza, i dati arrivano ma non
vanno live e la diretta parte solo aprendo la Live Control Room.

Questo modulo crea e collega il broadcast via API, impostando
enableAutoStart=true / enableAutoStop=false: la diretta parte da sola
quando ffmpeg inizia a pubblicare e sopravvive alle interruzioni di
pochi secondi dovute alla cattura della foto.
"""

import threading
from datetime import datetime, timedelta, timezone

import requests

TOKEN_URL = "https://oauth2.googleapis.com/token"
API_BASE = "https://www.googleapis.com/youtube/v3"
SCOPE = "https://www.googleapis.com/auth/youtube"

# Stati di un broadcast riutilizzabile: già in onda o pronto a partire.
REUSABLE_STATES = ("active", "upcoming")


class YouTubeLiveManager:
    """Crea, collega e riusa il liveBroadcast associato alla stream key."""

    def __init__(self, yt_config, stream_key, logger):
        self.logger = logger
        self.cfg = yt_config or {}
        self.stream_key = stream_key or ""
        self.timeout = self.cfg.get("timeout", 10)

        self._lock = threading.Lock()
        self._access_token = None
        self._token_expiry = datetime.now(timezone.utc)
        self._stream_id = None
        self._broadcast_id = None

        self.logger.info("YouTubeLiveManager object created")

    # --- Configurazione -------------------------------------------------

    def update_config(self, yt_config, stream_key):
        """Applica una nuova configurazione invalidando token e cache."""
        with self._lock:
            self.cfg = yt_config or {}
            self.stream_key = stream_key or ""
            self.timeout = self.cfg.get("timeout", 10)
            self._access_token = None
            self._token_expiry = datetime.now(timezone.utc)
            self._stream_id = None
            self._broadcast_id = None

    @property
    def enabled(self):
        return bool(self.cfg.get("enabled"))

    def _credentials_ok(self):
        missing = [k for k in ("client_id", "client_secret", "refresh_token") if not self.cfg.get(k)]
        if missing:
            self.logger.warning(f"YouTube Live enabled but missing config: {', '.join(missing)}")
            return False
        if not self.stream_key:
            self.logger.warning("YouTube Live enabled but streamParameters.yt_api_key is empty.")
            return False
        return True

    # --- OAuth ----------------------------------------------------------

    def _token(self):
        """Ritorna un access token valido, rinnovandolo se necessario."""
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

    # --- API ------------------------------------------------------------

    def _api(self, method, path, params=None, body=None):
        headers = {"Authorization": f"Bearer {self._token()}"}
        r = requests.request(
            method,
            f"{API_BASE}/{path}",
            headers=headers,
            params=params,
            json=body,
            timeout=self.timeout,
        )
        if r.status_code >= 400:
            raise RuntimeError(f"YouTube API {method} {path} failed ({r.status_code}): {r.text}")
        return r.json() if r.content else {}

    def _find_stream_id(self):
        """Trova l'id del liveStream corrispondente alla nostra stream key."""
        if self._stream_id:
            return self._stream_id

        data = self._api("GET", "liveStreams", params={
            "part": "id,snippet,cdn",
            "mine": "true",
            "maxResults": 50,
        })

        for item in data.get("items", []):
            name = item.get("cdn", {}).get("ingestionInfo", {}).get("streamName")
            if name == self.stream_key:
                self._stream_id = item["id"]
                title = item.get("snippet", {}).get("title", "?")
                self.logger.info(f"Matched YouTube liveStream '{title}' (id={self._stream_id})")
                return self._stream_id

        titles = [i.get("snippet", {}).get("title", "?") for i in data.get("items", [])]
        self.logger.error(
            "No YouTube liveStream matches the configured stream key. "
            f"Streams found on the account: {titles or 'none'}. "
            "Check streamParameters.yt_api_key against YouTube Studio."
        )
        return None

    def _find_bound_broadcast(self, stream_id):
        """Cerca un broadcast riutilizzabile già legato al nostro stream."""
        for status in REUSABLE_STATES:
            data = self._api("GET", "liveBroadcasts", params={
                "part": "id,snippet,status,contentDetails",
                "broadcastStatus": status,
                "broadcastType": "all",
                "maxResults": 50,
            })
            for item in data.get("items", []):
                if item.get("contentDetails", {}).get("boundStreamId") == stream_id:
                    self.logger.info(
                        f"Reusing YouTube broadcast '{item['snippet'].get('title')}' "
                        f"(id={item['id']}, status={status})"
                    )
                    return item
        return None

    def _build_title(self):
        now = datetime.now()
        title = self.cfg.get("title") or "Live"
        return (title
                .replace("{date}", now.strftime("%d/%m/%Y"))
                .replace("{time}", now.strftime("%H:%M")))

    def _create_broadcast(self):
        """Crea un broadcast con avvio automatico e senza interruzione automatica."""
        start = datetime.now(timezone.utc) + timedelta(minutes=1)
        body = {
            "snippet": {
                "title": self._build_title(),
                "description": self.cfg.get("description", ""),
                "scheduledStartTime": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
            "status": {
                "privacyStatus": self.cfg.get("privacy", "public"),
                "selfDeclaredMadeForKids": bool(self.cfg.get("made_for_kids", False)),
            },
            "contentDetails": {
                "enableAutoStart": True,
                "enableAutoStop": False,
                "enableDvr": bool(self.cfg.get("dvr", True)),
                "recordFromStart": bool(self.cfg.get("record", True)),
                "latencyPreference": self.cfg.get("latency", "low"),
                # Il monitor stream va disattivato, altrimenti l'avvio
                # automatico porta il broadcast in "testing" e non in onda.
                "monitorStream": {"enableMonitorStream": False},
            },
        }

        item = self._api("POST", "liveBroadcasts",
                         params={"part": "id,snippet,status,contentDetails"},
                         body=body)
        self.logger.info(f"Created YouTube broadcast '{body['snippet']['title']}' (id={item['id']})")
        return item

    def _bind(self, broadcast_id, stream_id):
        self._api("POST", "liveBroadcasts/bind", params={
            "id": broadcast_id,
            "streamId": stream_id,
            "part": "id,contentDetails",
        })
        self.logger.info(f"Bound broadcast {broadcast_id} to stream {stream_id}")

    # --- API pubblica ---------------------------------------------------

    def ensure_broadcast(self):
        """
        Garantisce che esista un broadcast pronto a ricevere il push RTMP.

        Va chiamata *prima* di avviare ffmpeg: il broadcast con
        enableAutoStart va in onda appena rileva i dati in ingresso.
        Non solleva mai eccezioni: ritorna True/False.
        """
        if not self.enabled:
            return False
        if not self._credentials_ok():
            return False

        with self._lock:
            try:
                stream_id = self._find_stream_id()
                if not stream_id:
                    return False

                broadcast = self._find_bound_broadcast(stream_id)
                if broadcast:
                    self._broadcast_id = broadcast["id"]
                    return True

                broadcast = self._create_broadcast()
                self._bind(broadcast["id"], stream_id)
                self._broadcast_id = broadcast["id"]
                self.logger.info("YouTube broadcast ready, waiting for RTMP ingestion to go live.")
                return True

            except requests.exceptions.RequestException as e:
                self.logger.error(f"YouTube Live network error: {e}")
            except Exception as e:
                self.logger.error(f"YouTube Live error: {e}", exc_info=True)
            return False

    def end_broadcast(self):
        """Chiude esplicitamente il broadcast corrente (usata allo shutdown)."""
        if not self.enabled or not self._broadcast_id:
            return False

        with self._lock:
            broadcast_id = self._broadcast_id
            try:
                self._api("POST", "liveBroadcasts/transition", params={
                    "id": broadcast_id,
                    "broadcastStatus": "complete",
                    "part": "id,status",
                })
                self.logger.info(f"YouTube broadcast {broadcast_id} completed.")
                self._broadcast_id = None
                return True
            except Exception as e:
                self.logger.error(f"Failed to complete YouTube broadcast {broadcast_id}: {e}")
                return False
