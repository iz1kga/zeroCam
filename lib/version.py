# -*- coding: utf-8 -*-
"""
Versione dell'applicazione.

Il valore arriva dal file VERSION, scritto dall'installatore con il tag
della release installata. Nei pacchetti prodotti da `git archive` il file
contiene già il tag grazie a export-subst; lavorando su un checkout di
sviluppo il segnaposto non viene sostituito, quindi si ripiega su
`git describe`.
"""

import os
import subprocess

VERSION_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'VERSION')

_cached_version = None


def get_version():
    """Ritorna la versione installata, o 'unknown' se non determinabile."""
    global _cached_version
    if _cached_version is not None:
        return _cached_version

    _cached_version = _read_version_file() or _describe_from_git() or 'unknown'
    return _cached_version


def _read_version_file():
    try:
        with open(VERSION_FILE, 'r') as f:
            value = f.read().strip()
    except OSError:
        return None
    # Segnaposto non sostituito: siamo in un checkout, oppure la versione di
    # git che ha creato l'archivio non conosce la direttiva. In entrambi i
    # casi il contenuto non è una versione e va ignorato.
    if not value or value.startswith('$Format') or value.startswith('%('):
        return None
    return value


def _describe_from_git():
    try:
        result = subprocess.run(
            ['git', 'describe', '--tags', '--always', '--dirty'],
            cwd=os.path.dirname(VERSION_FILE),
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip() or None
    except Exception:
        pass
    return None
