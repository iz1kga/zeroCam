# -*- coding: utf-8 -*-
"""
Materiale caricato dall'utente: audio e loghi.

I file stanno in <dati>/assets/<categoria>/, quindi sopravvivono agli
aggiornamenti come il resto dei dati. In configurazione non si scrive il
percorso ma un riferimento 'asset:categoria/nome': è indipendente da dove
è installata la webcam, così un backup della configurazione ripristinato
altrove continua a puntare al file giusto.

Il resto del programma non deve conoscere questa cartella: chiede qui il
percorso (per ffmpeg) o l'URL (per chi scarica i loghi con urllib).
"""

import os
import re
import unicodedata

from lib import paths

# Categorie ammesse e relative estensioni. Tenerle strette serve a due
# cose: non far caricare eseguibili e non far scegliere all'utente un file
# che ffmpeg poi rifiuta.
CATEGORIES = {
    "audio": {
        "label": "Audio",
        "extensions": (".mp3", ".aac", ".m4a", ".ogg", ".opus", ".wav", ".flac"),
    },
    "logo": {
        "label": "Loghi",
        "extensions": (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"),
    },
}

PREFIX = "asset:"
MAX_SIZE = 32 * 1024 * 1024

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


class AssetError(Exception):
    """Errore utente: nome, categoria o file non validi."""


def _category_dir(category):
    if category not in CATEGORIES:
        raise AssetError(f"Categoria sconosciuta: {category}")
    return os.path.join(paths.ASSETS_DIR, category)


def safe_name(name):
    """
    Nome di file utilizzabile, ricavato da quello caricato.

    Gli accenti diventano lettere semplici e tutto il resto che non sia
    alfanumerico un trattino: i nomi finiscono in una riga di comando di
    ffmpeg e in un filtergraph, dove spazi e apici fanno danni.
    """
    base = os.path.basename(name or "").strip()
    base = unicodedata.normalize("NFKD", base).encode("ascii", "ignore").decode("ascii")
    base = _SAFE_NAME.sub("-", base).strip("-._")
    if not base or base.startswith("."):
        raise AssetError("Nome del file non valido.")
    return base[:100]


def check_extension(category, name):
    allowed = CATEGORIES[category]["extensions"]
    if not name.lower().endswith(allowed):
        raise AssetError(
            f"Estensione non ammessa per {CATEGORIES[category]['label'].lower()}: "
            f"sono accettati {', '.join(allowed)}"
        )


def reference(category, name):
    """Il valore da salvare in configurazione."""
    return f"{PREFIX}{category}/{name}"


def parse(value):
    """
    Scompone un riferimento in (categoria, nome).

    Ritorna None per qualsiasi altra cosa - un URL http, un percorso
    assoluto, una stringa vuota - che il chiamante deve trattare come
    prima. Il nome viene ripulito: un '..' arrivato da una configurazione
    scritta a mano non deve poter uscire dalla cartella.
    """
    if not value or not str(value).startswith(PREFIX):
        return None
    body = str(value)[len(PREFIX):]
    category, _, name = body.partition("/")
    if category not in CATEGORIES or not name:
        return None
    name = os.path.basename(name)
    if not name or name in (".", ".."):
        return None
    return category, name


def path(value):
    """
    Percorso su disco di un riferimento, o None se non esiste.

    Il file può mancare: un asset cancellato lascia in configurazione un
    riferimento morto, che chi lo usa deve saper ignorare.
    """
    parsed = parse(value)
    if not parsed:
        return None
    candidate = os.path.join(_category_dir(parsed[0]), parsed[1])
    return candidate if os.path.isfile(candidate) else None


def resolve_url(value):
    """
    URL scaricabile con urllib per chi legge i loghi.

    Un riferimento diventa un file://, tutto il resto resta com'è: gli URL
    http configurati prima degli assets continuano a funzionare.
    """
    local = path(value)
    if local:
        return "file://" + local
    return value


def listing(category=None):
    """Elenco degli asset, ordinato per categoria e nome."""
    items = []
    for name in sorted(CATEGORIES) if category is None else [category]:
        if name not in CATEGORIES:
            raise AssetError(f"Categoria sconosciuta: {name}")
        directory = os.path.join(paths.ASSETS_DIR, name)
        if not os.path.isdir(directory):
            continue
        for filename in sorted(os.listdir(directory)):
            full = os.path.join(directory, filename)
            if not os.path.isfile(full) or filename.startswith("."):
                continue
            stat = os.stat(full)
            items.append({
                "category": name,
                "name": filename,
                "reference": reference(name, filename),
                "size": stat.st_size,
                "modified": int(stat.st_mtime),
            })
    return items


def save(category, filename, stream):
    """Scrive un file caricato e ritorna la sua voce di elenco."""
    directory = _category_dir(category)
    name = safe_name(filename)
    check_extension(category, name)

    os.makedirs(directory, exist_ok=True)
    target = os.path.join(directory, name)
    stream.save(target)

    size = os.path.getsize(target)
    if size == 0:
        os.remove(target)
        raise AssetError("Il file caricato è vuoto.")
    if size > MAX_SIZE:
        os.remove(target)
        raise AssetError(f"Il file supera il limite di {MAX_SIZE // (1024 * 1024)} MB.")

    return {
        "category": category,
        "name": name,
        "reference": reference(category, name),
        "size": size,
        "modified": int(os.path.getmtime(target)),
    }


def delete(category, name):
    """Cancella un asset. Ritorna False se non c'era."""
    directory = _category_dir(category)
    target = os.path.join(directory, os.path.basename(name or ""))
    if not os.path.isfile(target):
        return False
    os.remove(target)
    return True
