# -*- coding: utf-8 -*-
"""
Timelapse settimanale.

Ogni scatto lascia una copia ridimensionata in una cartella dedicata:
l'archivio di debug (cameraParameters.archiveImages) è un'altra cosa e di
norma è spento, quindi il timelapse tiene i propri fotogrammi.

I frame sono salvati già alla risoluzione del video finale, così il
montaggio è veloce e lo spazio occupato è prevedibile. Una volta a
settimana ffmpeg li monta e il video viene caricato su YouTube con le
stesse credenziali OAuth della diretta.
"""

import glob
import io
import os
import re
import shutil
import subprocess
import tempfile
import threading
from datetime import datetime, timedelta

import requests
from PIL import Image

from lib import assets, exif, paths
from lib.version import get_version
from lib.youtube_auth import UPLOAD_BASE

FRAME_PATTERN = "%Y%m%d-%H%M%S"
# \Z e non $: quest'ultimo accetterebbe anche un a capo finale, e su Linux
# un nome di file può contenerlo.
FRAME_REGEX = re.compile(r"\A\d{8}-\d{6}\.jpg\Z")
# Blocchi da 8 MiB: multiplo di 256 KiB come richiesto dall'upload resumable.
CHUNK_SIZE = 8 * 1024 * 1024


class TimelapseManager:
    """Conserva i fotogrammi, monta il video settimanale e lo pubblica."""

    def __init__(self, config, auth, logger):
        self.logger = logger
        self.cfg = config or {}
        self.auth = auth
        self._build_lock = threading.Lock()
        self.last_result = None
        self.logger.info("TimelapseManager object created")

    def update_config(self, config):
        self.cfg = config or {}

    @property
    def enabled(self):
        return bool(self.cfg.get("enabled"))

    @property
    def frames_dir(self):
        # I percorsi relativi rimasti in configurazione ('./timelapse_frames')
        # puntavano dentro la cartella dell'applicazione, che l'aggiornamento
        # cancella: vengono riportati nella cartella dei dati.
        return paths.resolve(self.cfg.get("frames_dir"), paths.TIMELAPSE_FRAMES_DIR)

    @property
    def output_dir(self):
        return paths.resolve(self.cfg.get("output_dir"), paths.TIMELAPSE_OUTPUT_DIR)

    # --- Raccolta dei fotogrammi ----------------------------------------

    def store_frame(self, image_buffer, metadata=None, description="", manual_white_balance=False):
        """
        Salva una copia ridimensionata dello scatto appena elaborato.

        Riceve il buffer dell'immagine finale (ritagliata, mascherata e
        annotata), così il timelapse mostra esattamente ciò che viene
        pubblicato. Non solleva mai: un errore qui non deve far fallire
        il ciclo di cattura.

        I metadati della cattura vengono riscritti come EXIF: il
        ridimensionamento con PIL li perderebbe, e senza di essi un
        fotogramma non dice piu' con quale esposizione o con quali
        guadagni di bianco e' stato preso.
        """
        if not self.enabled:
            return None

        try:
            os.makedirs(self.frames_dir, exist_ok=True)
            image_buffer.seek(0)
            image = Image.open(image_buffer)
            image = image.convert("RGB")

            width = int(self.cfg.get("frame_width", 2560))
            if image.width > width:
                height = round(image.height * width / image.width)
                # yuv420p richiede dimensioni pari
                image = image.resize((width - width % 2, height - height % 2), Image.LANCZOS)

            now = datetime.now()
            path = os.path.join(self.frames_dir, now.strftime(FRAME_PATTERN) + ".jpg")
            exif_bytes = exif.build(
                metadata, now, description=description,
                software=f"zeroCAM {get_version()}",
                manual_white_balance=manual_white_balance,
            )
            image.save(path, format="JPEG",
                       quality=int(self.cfg.get("frame_quality", 88)),
                       exif=exif_bytes)
            self.logger.debug(f"Timelapse frame stored: {path}")
            return path
        except Exception as e:
            self.logger.error(f"Failed to store timelapse frame: {e}", exc_info=True)
            return None
        finally:
            image_buffer.seek(0)

    def list_frames(self):
        """Fotogrammi disponibili, in ordine cronologico."""
        try:
            names = [n for n in os.listdir(self.frames_dir) if FRAME_REGEX.match(n)]
        except OSError:
            return []
        # Il nome è YYYYMMDD-HHMMSS: l'ordine alfabetico è quello cronologico.
        return [os.path.join(self.frames_dir, n) for n in sorted(names)]

    def days(self):
        """Giorni con fotogrammi disponibili, dal più recente, con il conteggio."""
        counts = {}
        for path in self.list_frames():
            day = os.path.basename(path)[:8]
            counts[day] = counts.get(day, 0) + 1
        return [
            {"day": f"{d[:4]}-{d[4:6]}-{d[6:8]}", "count": c}
            for d, c in sorted(counts.items(), reverse=True)
        ]

    def frames_for_day(self, day):
        """Nomi dei fotogrammi di un giorno (YYYY-MM-DD), in ordine cronologico."""
        prefix = day.replace("-", "")
        if not prefix.isdigit() or len(prefix) != 8:
            return []
        return [
            os.path.basename(p) for p in self.list_frames()
            if os.path.basename(p).startswith(prefix)
        ]

    def frame_path(self, name):
        """
        Percorso assoluto di un fotogramma, o None se il nome non è valido.

        Il nome arriva da una richiesta HTTP: viene accettato solo se
        corrisponde esattamente al formato dei fotogrammi, così non può
        contenere separatori di percorso.
        """
        if not FRAME_REGEX.match(name or ""):
            return None
        path = os.path.join(os.path.abspath(self.frames_dir), name)
        return path if os.path.exists(path) else None

    def stats(self):
        """Numero di fotogrammi e spazio occupato, per l'interfaccia web."""
        frames = self.list_frames()
        size = 0
        for path in frames:
            try:
                size += os.path.getsize(path)
            except OSError:
                pass
        return {
            "frames": len(frames),
            "bytes": size,
            "oldest": os.path.basename(frames[0]) if frames else None,
            "newest": os.path.basename(frames[-1]) if frames else None,
            "last_result": self.last_result,
        }

    def cleanup_old_frames(self):
        """Elimina i fotogrammi oltre la finestra di ritenzione."""
        weeks = int(self.cfg.get("retention_weeks", 4))
        if weeks <= 0:
            return 0

        cutoff = datetime.now() - timedelta(weeks=weeks)
        removed = 0
        for path in self.list_frames():
            try:
                stamp = datetime.strptime(os.path.basename(path)[:-4], FRAME_PATTERN)
            except ValueError:
                continue
            if stamp < cutoff:
                try:
                    os.remove(path)
                    removed += 1
                except OSError as e:
                    self.logger.warning(f"Could not remove old frame {path}: {e}")

        if removed:
            self.logger.info(f"Timelapse retention: removed {removed} frames older than {weeks} weeks.")
        return removed

    # --- Montaggio -------------------------------------------------------

    def _audio_arguments(self):
        """
        Ingresso e codifica dell'audio di sottofondo, se configurato.

        Il brano viene ripetuto per tutta la durata del video e tagliato
        alla fine dei fotogrammi: '-shortest' guarda al flusso più corto,
        che con il loop infinito è sempre il video.
        """
        source = self.cfg.get("audio_file", "") or ""
        track = assets.path(source)
        if not track:
            if source:
                self.logger.warning(
                    f"Timelapse audio '{source}' not found among the assets: building it silent."
                )
            return []

        try:
            volume = max(0, min(100, int(self.cfg.get("audio_volume", 100))))
        except (TypeError, ValueError):
            volume = 100

        self.logger.info(f"Timelapse audio: {os.path.basename(track)} at {volume}% volume.")
        arguments = ["-stream_loop", "-1", "-i", track,
                     "-map", "0:v", "-map", "1:a", "-shortest",
                     "-c:a", "aac", "-b:a", "192k"]
        if volume != 100:
            arguments += ["-af", f"volume={volume / 100:.2f}"]
        return arguments

    def build_video(self, frames):
        """
        Monta i fotogrammi in un mp4 e ritorna il percorso del file.

        I file sono collegati in una cartella temporanea con nomi
        progressivi: ffmpeg vuole una sequenza numerata continua, mentre i
        nostri nomi sono orari e possono avere buchi.
        """
        os.makedirs(self.output_dir, exist_ok=True)
        output = os.path.join(
            self.output_dir,
            f"timelapse-{datetime.now().strftime('%Y%m%d-%H%M%S')}.mp4"
        )

        staging = tempfile.mkdtemp(prefix="zerocam-timelapse-")
        try:
            for index, source in enumerate(frames):
                link = os.path.join(staging, f"f{index:06d}.jpg")
                try:
                    os.symlink(os.path.abspath(source), link)
                except OSError:
                    # Filesystem senza symlink: si ripiega sulla copia
                    shutil.copy2(source, link)

            command = [
                "nice", "-n", str(self.cfg.get("nice", 19)),
                "ffmpeg", "-y",
                "-framerate", str(self.cfg.get("fps", 25)),
                "-i", os.path.join(staging, "f%06d.jpg"),
            ] + self._audio_arguments() + [
                "-c:v", "libx264",
                "-preset", str(self.cfg.get("preset", "medium")),
                "-crf", str(self.cfg.get("crf", 20)),
                "-pix_fmt", "yuv420p",
                "-threads", str(self.cfg.get("threads", 2)),
                "-movflags", "+faststart",
                output,
            ]

            self.logger.info(f"Encoding timelapse from {len(frames)} frames...")
            result = subprocess.run(command, capture_output=True, text=True,
                                    timeout=self.cfg.get("encode_timeout", 7200))
            if result.returncode != 0:
                tail = (result.stderr or "").strip().splitlines()[-5:]
                raise RuntimeError("ffmpeg failed: " + " | ".join(tail))

            size_mb = os.path.getsize(output) / (1024 * 1024)
            self.logger.info(f"Timelapse encoded: {output} ({size_mb:.1f} MB)")
            return output
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    # --- Pubblicazione ---------------------------------------------------

    def _video_metadata(self, frames):
        first = self._frame_time(frames[0])
        last = self._frame_time(frames[-1])

        def fill(text):
            return (text or "")\
                .replace("{from}", first.strftime("%d/%m/%Y"))\
                .replace("{to}", last.strftime("%d/%m/%Y"))\
                .replace("{date}", last.strftime("%d/%m/%Y"))\
                .replace("{frames}", str(len(frames)))

        return {
            "snippet": {
                "title": fill(self.cfg.get("title") or "Timelapse {from} - {to}"),
                "description": fill(self.cfg.get("description", "")),
                "categoryId": str(self.cfg.get("category_id", 22)),
            },
            "status": {
                "privacyStatus": self.cfg.get("privacy", "public"),
                "selfDeclaredMadeForKids": bool(self.cfg.get("made_for_kids", False)),
            },
        }

    @staticmethod
    def _frame_time(path):
        return datetime.strptime(os.path.basename(path)[:-4], FRAME_PATTERN)

    def upload_video(self, path, metadata):
        """
        Carica il video con l'upload resumable.

        Il caricamento avviene a blocchi: su una connessione domestica un
        video da decine di MB non arriva sempre al primo tentativo, e
        ripartire dal punto raggiunto evita di ricominciare da capo.
        """
        size = os.path.getsize(path)
        session = requests.post(
            f"{UPLOAD_BASE}/videos",
            params={"uploadType": "resumable", "part": "snippet,status"},
            headers=self.auth.headers({
                "Content-Type": "application/json; charset=UTF-8",
                "X-Upload-Content-Type": "video/mp4",
                "X-Upload-Content-Length": str(size),
            }),
            json=metadata,
            timeout=self.cfg.get("timeout", 30),
        )
        if session.status_code >= 400:
            raise RuntimeError(f"Upload session failed ({session.status_code}): {session.text}")

        session_uri = session.headers.get("Location")
        if not session_uri:
            raise RuntimeError("Upload session did not return a Location header.")

        self.logger.info(f"Uploading {size / (1024 * 1024):.1f} MB to YouTube...")
        offset = 0
        attempts = 0
        with open(path, "rb") as video:
            while offset < size:
                video.seek(offset)
                chunk = video.read(CHUNK_SIZE)
                end = offset + len(chunk) - 1

                response = requests.put(
                    session_uri,
                    headers={
                        "Content-Length": str(len(chunk)),
                        "Content-Range": f"bytes {offset}-{end}/{size}",
                    },
                    data=chunk,
                    timeout=self.cfg.get("upload_timeout", 300),
                )

                if response.status_code in (200, 201):
                    video_id = response.json().get("id")
                    self.logger.info(f"Timelapse published: https://youtu.be/{video_id}")
                    return video_id

                if response.status_code == 308:
                    # Blocco accettato: l'header Range dice dove ripartire.
                    offset = self._resume_offset(response, offset + len(chunk))
                    attempts = 0
                    self.logger.debug(f"Upload progress: {offset / size * 100:.0f}%")
                    continue

                attempts += 1
                if response.status_code >= 500 and attempts <= 3:
                    self.logger.warning(
                        f"Upload chunk failed ({response.status_code}), retry {attempts}/3."
                    )
                    continue

                raise RuntimeError(f"Upload failed ({response.status_code}): {response.text}")

        raise RuntimeError("Upload ended without a response from YouTube.")

    @staticmethod
    def _resume_offset(response, fallback):
        received = response.headers.get("Range")
        if received and "-" in received:
            try:
                return int(received.split("-")[-1]) + 1
            except ValueError:
                pass
        return fallback

    # --- Orchestrazione --------------------------------------------------

    def run(self, upload=True):
        """
        Monta e pubblica il timelapse. Ritorna un riepilogo dell'esito.

        Non solleva eccezioni: è invocata da un job schedulato e da
        un'azione dell'interfaccia web, che devono sopravvivere a un
        fallimento.
        """
        if not self._build_lock.acquire(blocking=False):
            self.logger.warning("A timelapse build is already running, skipping.")
            return {"ok": False, "error": "already running"}

        try:
            frames = self.list_frames()
            minimum = int(self.cfg.get("min_frames", 30))
            if len(frames) < minimum:
                message = f"only {len(frames)} frames available, {minimum} required"
                self.logger.warning(f"Timelapse skipped: {message}.")
                return {"ok": False, "error": message}

            video = self.build_video(frames)
            result = {"ok": True, "frames": len(frames), "video": video}

            if upload:
                if not self.auth.configured:
                    missing = ", ".join(self.auth.missing_keys())
                    self.logger.error(f"Timelapse not uploaded, missing credentials: {missing}")
                    # Il video c'è, ma l'operazione richiesta non è riuscita:
                    # l'esito non va segnalato come positivo.
                    result["ok"] = False
                    result["error"] = f"missing credentials: {missing}"
                else:
                    result["video_id"] = self.upload_video(video, self._video_metadata(frames))

            if not self.cfg.get("keep_local", True):
                try:
                    os.remove(video)
                    result.pop("video", None)
                except OSError:
                    pass

            self.cleanup_old_frames()
            self.last_result = {**result, "at": datetime.now().strftime("%d-%m-%Y %H:%M:%S")}
            return result

        except Exception as e:
            self.logger.error(f"Timelapse failed: {e}", exc_info=True)
            self.last_result = {
                "ok": False, "error": str(e),
                "at": datetime.now().strftime("%d-%m-%Y %H:%M:%S"),
            }
            return {"ok": False, "error": str(e)}
        finally:
            self._build_lock.release()
