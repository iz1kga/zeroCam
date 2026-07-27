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

Un broadcast riutilizzabile viene riusato all'infinito, a meno che sia
configurata l'ora di reset giornaliero (youtubeLive.daily_reset_time):
in quel caso la diretta nata prima di quell'ora viene chiusa e
rimpiazzata da una nuova al primo scatto successivo.
"""

import threading
from datetime import datetime, time as dtime, timedelta, timezone

import requests

from lib.youtube_auth import YouTubeAuth

# Stati di un broadcast riutilizzabile: già in onda o pronto a partire.
REUSABLE_STATES = ("active", "upcoming")


def _parse_iso(value):
    """Converte un timestamp ISO 8601 di YouTube in datetime aware (UTC)."""
    if not value:
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _parse_hhmm(value):
    """Converte 'HH:MM' in un oggetto time; None se vuoto o malformato."""
    if not value:
        return None
    try:
        hour, minute = str(value).strip().split(":")
        return dtime(int(hour), int(minute))
    except (ValueError, AttributeError):
        return None


class YouTubeLiveManager:
    """Crea, collega e riusa il liveBroadcast associato alla stream key."""

    def __init__(self, yt_config, stream_key, logger, auth=None):
        self.logger = logger
        self.cfg = yt_config or {}
        self.stream_key = stream_key or ""
        self.auth = auth or YouTubeAuth(self.cfg, logger)

        self._lock = threading.Lock()
        self._stream_id = None
        self._broadcast_id = None

        self.logger.info("YouTubeLiveManager object created")

    # --- Configurazione -------------------------------------------------

    def update_config(self, yt_config, stream_key):
        """Applica una nuova configurazione invalidando la cache."""
        with self._lock:
            self.cfg = yt_config or {}
            self.stream_key = stream_key or ""
            self._stream_id = None
            self._broadcast_id = None

    @property
    def enabled(self):
        return bool(self.cfg.get("enabled"))

    def _credentials_ok(self):
        missing = self.auth.missing_keys()
        if missing:
            self.logger.warning(f"YouTube Live enabled but missing config: {', '.join(missing)}")
            return False
        if not self.stream_key:
            self.logger.warning("YouTube Live enabled but streamParameters.yt_api_key is empty.")
            return False
        return True

    # --- API ------------------------------------------------------------

    def _api(self, method, path, params=None, body=None):
        return self.auth.api(method, path, params=params, body=body)

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
                        f"Found YouTube broadcast '{item['snippet'].get('title')}' "
                        f"bound to the stream (id={item['id']}, status={status})"
                    )
                    return item
        return None

    def _rollover_boundary(self):
        """
        Ultimo passaggio dell'ora di reset giornaliero (locale, aware).

        Ritorna None se il reset è disattivato: in quel caso il broadcast
        esistente viene riusato all'infinito, come prima.
        """
        reset = _parse_hhmm(self.cfg.get("daily_reset_time"))
        if reset is None:
            return None

        now = datetime.now().astimezone()
        boundary = now.replace(hour=reset.hour, minute=reset.minute,
                               second=0, microsecond=0)
        if boundary > now:
            boundary -= timedelta(days=1)
        return boundary

    def _rollover_note(self):
        """Spiega nel log perché un broadcast viene riusato invece che ricreato."""
        configured = str(self.cfg.get("daily_reset_time") or "").strip()
        if _parse_hhmm(configured) is None:
            if configured:
                return f"daily reset '{configured}' is not a valid HH:MM, rollover disabled"
            return "daily reset not configured"
        boundary = self._rollover_boundary()
        return f"started after the daily reset of {boundary.strftime('%d/%m/%Y %H:%M')}"

    def _is_stale(self, broadcast):
        """True se il broadcast è nato prima dell'ultima ora di reset."""
        boundary = self._rollover_boundary()
        if boundary is None:
            return False

        snippet = broadcast.get("snippet", {})
        started = (_parse_iso(snippet.get("actualStartTime"))
                   or _parse_iso(snippet.get("scheduledStartTime"))
                   or _parse_iso(snippet.get("publishedAt")))
        if started is None:
            # Senza data affidabile meglio riusarlo che ricrearlo a ogni scatto.
            self.logger.warning(
                f"Broadcast {broadcast.get('id')} has no usable start time, skipping daily reset."
            )
            return False

        if started >= boundary:
            return False

        self.logger.info(
            f"Broadcast {broadcast.get('id')} started at {started.astimezone().strftime('%d/%m/%Y %H:%M')}, "
            f"before the daily reset of {boundary.strftime('%d/%m/%Y %H:%M')}: creating a new one."
        )
        return True

    def _retire(self, broadcast):
        """
        Toglie di mezzo un broadcast scaduto.

        Se è in onda lo si porta a 'complete'; se non è mai partito lo si
        elimina, perché la transizione su un broadcast 'upcoming' fallisce.
        """
        broadcast_id = broadcast.get("id")
        lifecycle = broadcast.get("status", {}).get("lifeCycleStatus")
        try:
            if lifecycle == "upcoming":
                self._api("DELETE", "liveBroadcasts", params={"id": broadcast_id})
                self.logger.info(f"Deleted stale YouTube broadcast {broadcast_id} (never went live).")
            else:
                self._api("POST", "liveBroadcasts/transition", params={
                    "id": broadcast_id,
                    "broadcastStatus": "complete",
                    "part": "id,status",
                })
                self.logger.info(f"Completed stale YouTube broadcast {broadcast_id}.")
        except Exception as e:
            # Il bind del nuovo broadcast stacca comunque il vecchio dallo
            # stream, quindi si può proseguire.
            self.logger.warning(f"Could not retire stale broadcast {broadcast_id}: {e}")

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
                if broadcast and self._is_stale(broadcast):
                    self._retire(broadcast)
                    if self._broadcast_id == broadcast["id"]:
                        self._broadcast_id = None
                    broadcast = None

                if broadcast:
                    self._broadcast_id = broadcast["id"]
                    self.logger.info(
                        f"Reusing YouTube broadcast {self._broadcast_id} ({self._rollover_note()})."
                    )
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
