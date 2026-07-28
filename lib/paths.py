# -*- coding: utf-8 -*-
"""
Percorsi dei dati persistenti.

L'aggiornamento del software cancella e riscrive la cartella
dell'applicazione (zerocam_install fa `rm -rf` su di essa), quindi tutto
ciò che deve sopravvivere sta fuori, in una cartella 'data' accanto:

    /usr/local/zerocam/app     codice, sostituito a ogni aggiornamento
    /usr/local/zerocam/data    configurazione, log, fotogrammi, immagini

Fuori dall'installazione standard - per esempio girando dal repository -
i dati finiscono in 'data' dentro la cartella del progetto, così non si
sporca la directory superiore. ZEROCAM_DATA_DIR ha comunque l'ultima
parola.
"""

import os
import shutil

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _resolve_data_dir():
    override = os.getenv("ZEROCAM_DATA_DIR")
    if override:
        return os.path.abspath(override)
    if os.path.basename(APP_DIR) == "app":
        return os.path.join(os.path.dirname(APP_DIR), "data")
    return os.path.join(APP_DIR, "data")


DATA_DIR = _resolve_data_dir()


def data_path(*parts):
    return os.path.join(DATA_DIR, *parts)


CONFIG_FILE = data_path(".conf.json")
PRIVACY_MASK_FILE = data_path(".privacy_mask.json")
CAPTURE_INFO_FILE = data_path(".capture_info")
LATEST_IMAGE = data_path("latest.jpg")
LOG_DIR = data_path("logs")
LOG_FILE = os.path.join(LOG_DIR, "zerocam.log")
# Storico delle statistiche hardware: sta accanto ai log perché è lì che è
# sempre stato, e la cartella intera viene migrata in un colpo solo.
STATS_FILE = os.path.join(LOG_DIR, "stats.json")
IMAGES_DIR = data_path("images")
TIMELAPSE_FRAMES_DIR = data_path("timelapse_frames")
TIMELAPSE_OUTPUT_DIR = data_path("timelapse")
# Materiale caricato dall'utente: audio per diretta e timelapse, loghi per
# la sovraimpressione. Sta fra i dati perché un aggiornamento non deve
# portarselo via.
ASSETS_DIR = data_path("assets")
# Certificato TLS autofirmato dell'interfaccia: sta fra i dati perché
# rigenerarlo a ogni aggiornamento significherebbe far ricomparire
# l'avviso del browser a chi l'ha già accettato una volta.
CERT_DIR = data_path("certs")
CERT_FILE = os.path.join(CERT_DIR, "zerocam.crt")
KEY_FILE = os.path.join(CERT_DIR, "zerocam.key")
# Copia di quanto l'applicazione porta con sé: viene versata negli assets
# al primo avvio, così è disponibile senza che l'utente carichi nulla.
BUNDLED_ASSETS_DIR = os.path.join(APP_DIR, "assets")

# La memoria condivisa resta dentro l'applicazione: è un tmpfs montato lì da
# /etc/fstab e il suo contenuto è per definizione volatile.
SHMEM_DIR = os.path.join(APP_DIR, "shmem")
STREAM_PREVIEW = os.path.join(SHMEM_DIR, "stream_latest.jpg")

# Quanto veniva tenuto nella cartella dell'applicazione fino alla versione
# precedente e va spostato al primo avvio.
LEGACY_ENTRIES = (
    ".conf.json",
    ".privacy_mask.json",
    ".capture_info",
    "latest.jpg",
    "logs",
    "images",
    "timelapse_frames",
    "timelapse",
)


def seed_bundled_assets():
    """
    Copia negli assets dell'utente quelli distribuiti con l'applicazione.

    Solo i file mancanti: quello che l'utente ha cancellato resta
    cancellato, e un file con lo stesso nome non viene sovrascritto a ogni
    aggiornamento. Ritorna i messaggi da mandare a log.
    """
    messages = []
    if not os.path.isdir(BUNDLED_ASSETS_DIR):
        return messages

    for category in sorted(os.listdir(BUNDLED_ASSETS_DIR)):
        source_dir = os.path.join(BUNDLED_ASSETS_DIR, category)
        if not os.path.isdir(source_dir):
            continue
        target_dir = os.path.join(ASSETS_DIR, category)
        for name in sorted(os.listdir(source_dir)):
            source = os.path.join(source_dir, name)
            target = os.path.join(target_dir, name)
            if not os.path.isfile(source) or os.path.exists(target):
                continue
            try:
                os.makedirs(target_dir, exist_ok=True)
                shutil.copy2(source, target)
                messages.append(f"Installed the bundled asset {category}/{name}.")
            except Exception as e:
                messages.append(f"Could not install the bundled asset {category}/{name}: {e}")

    return messages


def resolve(value, default):
    """
    Percorso configurabile, riportato dentro la cartella dei dati.

    Un valore assoluto viene rispettato così com'è; uno relativo - come il
    vecchio './timelapse_frames' rimasto nelle configurazioni esistenti -
    viene agganciato a DATA_DIR invece che alla directory di lavoro.
    """
    if not value:
        return default
    if os.path.isabs(value):
        return value
    return os.path.normpath(os.path.join(DATA_DIR, value))


def migrate_legacy_data():
    """
    Sposta nella cartella dei dati quanto resta in quella dell'applicazione.

    Va chiamata prima di leggere configurazione o log. Ritorna i messaggi
    da mandare a log: a quel punto il logger non esiste ancora, perché il
    suo file sta proprio in una delle cartelle da spostare.
    """
    messages = []
    os.makedirs(DATA_DIR, exist_ok=True)

    for name in LEGACY_ENTRIES:
        source = os.path.join(APP_DIR, name)
        target = data_path(name)
        if not os.path.exists(source) or os.path.islink(source):
            continue
        if os.path.exists(target):
            messages.append(f"Both {source} and {target} exist: leaving the old copy alone.")
            continue
        try:
            shutil.move(source, target)
            messages.append(f"Moved {name} to the data directory ({target}).")
        except Exception as e:
            messages.append(f"Could not move {source} to {target}: {e}")

    return messages
