# -*- coding: utf-8 -*-
"""
Backup e ripristino della configurazione (disaster recovery).

I segreti sul disco sono cifrati con ZEROCAM_SECRET_KEY: copiare il
.conf.json così com'è darebbe un backup inutile su un'installazione
nuova, dove quella chiave non c'è più. Qui il backup viene quindi
costruito dalla configurazione *decifrata* e ricifrato subito con una
passphrase scelta dall'utente (PBKDF2-SHA256 + Fernet, salt casuale):
il file resta portabile ma non contiene password in chiaro.

La sezione security (hash della password web e chiave di sessione
Flask) è esclusa: un backup vecchio rimetterebbe in uso credenziali di
login superate, chiudendo fuori chi ripristina.
"""

import base64
import json
import os
from datetime import datetime, timezone

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

BACKUP_FORMAT = 1
KDF_ITERATIONS = 200000
MIN_PASSPHRASE_LEN = 8

# Sezioni che restano quelle della macchina su cui si ripristina.
EXCLUDED_SECTIONS = ("security",)


class BackupError(Exception):
    """Errore mostrabile all'utente (passphrase errata, file non valido...)."""


def _fernet(passphrase, salt, iterations):
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=iterations,
    )
    return Fernet(base64.urlsafe_b64encode(kdf.derive(passphrase.encode())))


def build(config, privacy_mask, passphrase, version=""):
    """
    Costruisce l'envelope da scaricare.

    `config` è la configurazione decifrata: i segreti escono in chiaro dal
    config manager e vengono ricifrati qui con la passphrase.
    """
    if not passphrase or len(passphrase) < MIN_PASSPHRASE_LEN:
        raise BackupError(f"The passphrase must be at least {MIN_PASSPHRASE_LEN} characters long.")

    payload = {
        "config": {k: v for k, v in (config or {}).items() if k not in EXCLUDED_SECTIONS},
        "privacy_mask": privacy_mask if privacy_mask is not None else [],
    }
    salt = os.urandom(16)
    token = _fernet(passphrase, salt, KDF_ITERATIONS).encrypt(json.dumps(payload).encode())

    return {
        "zerocam_backup": BACKUP_FORMAT,
        "created": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "version": version,
        "encrypted": True,
        "kdf": {
            "algo": "pbkdf2-sha256",
            "iterations": KDF_ITERATIONS,
            "salt": base64.b64encode(salt).decode(),
        },
        "payload": token.decode(),
    }


def read(envelope, passphrase):
    """
    Apre un envelope e ritorna (config, privacy_mask).

    privacy_mask è None quando il backup non ne conteneva una, così il
    chiamante distingue "nessuna maschera nel file" da "maschera vuota".
    """
    if not isinstance(envelope, dict):
        raise BackupError("Invalid backup file.")

    fmt = envelope.get("zerocam_backup")
    if fmt is None:
        raise BackupError("The file is not a zeroCAM backup.")
    if fmt > BACKUP_FORMAT:
        raise BackupError(f"Backup in format {fmt}, too recent for this version.")
    if not passphrase:
        raise BackupError("A passphrase is required to open the backup.")

    kdf = envelope.get("kdf") or {}
    try:
        salt = base64.b64decode(kdf.get("salt", ""), validate=True)
        iterations = int(kdf.get("iterations", KDF_ITERATIONS))
        token = envelope["payload"].encode()
    except (KeyError, AttributeError, ValueError, TypeError):
        raise BackupError("Backup file incomplete or damaged.")

    if not salt or iterations < 1:
        raise BackupError("Backup file incomplete or damaged.")

    try:
        plain = _fernet(passphrase, salt, iterations).decrypt(token)
    except InvalidToken:
        raise BackupError("Wrong passphrase, or the backup file has been tampered with.")

    try:
        payload = json.loads(plain.decode())
    except (ValueError, UnicodeDecodeError):
        raise BackupError("The backup content is unreadable.")

    config = payload.get("config")
    if not isinstance(config, dict) or not config:
        raise BackupError("The backup does not hold a valid configuration.")

    mask = payload.get("privacy_mask")
    if mask is not None and not isinstance(mask, list):
        mask = None

    # Difesa in profondità: anche un file confezionato a mano non deve poter
    # sostituire le credenziali di accesso all'interfaccia.
    for section in EXCLUDED_SECTIONS:
        config.pop(section, None)

    return config, mask
