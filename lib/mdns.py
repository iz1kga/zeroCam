# -*- coding: utf-8 -*-
"""
Annuncio del servizio web su mDNS.

L'hostname del dispositivo lo annuncia già Avahi per conto suo, ed è quello
che si digita nel browser: `zerocam-a1b2.local`. Ma un hostname è una label
DNS, quindi minuscolo e senza spazi, e non è un buon nome da leggere.

Qui si aggiunge l'altra metà: l'annuncio del servizio `_http._tcp`, che è
ciò che compare nei browser Bonjour e nella sezione *Rete* dei gestori di
file. Quello può portare il nome vero della webcam — "Villar Focchiardo" —
perché non ha i vincoli di un hostname.

L'annuncio è un file XML in /etc/avahi/services, che Avahi sorveglia con
inotify e ricarica da sé: non serve riavviarlo né parlargli. Il file
appartiene all'utente del servizio, creato così dall'installazione, per
poterlo riscrivere quando il nome cambia senza chiedere privilegi.
"""

import os
import socket
from xml.sax.saxutils import escape

# Il percorso è sovrascrivibile perché i test non devono scrivere in /etc.
SERVICE_FILE = os.getenv("ZEROCAM_AVAHI_SERVICE", "/etc/avahi/services/zerocam.service")

TEMPLATE = """<?xml version="1.0" standalone='no'?>
<!DOCTYPE service-group SYSTEM "avahi-service.dtd">
<!-- Scritto da zeroCAM: le modifiche a mano vengono sovrascritte. -->
<service-group>
  <name>{name}</name>
  <service>
    <type>_http._tcp</type>
    <port>{port}</port>
    <txt-record>path=/</txt-record>
  </service>
</service-group>
"""


def service_name(config):
    """
    Il nome con cui la webcam si presenta sulla rete.

    Quello di Device Details, che è come l'utente la chiama. Vuoto o
    assente, si ripiega sull'hostname, che c'è sempre.
    """
    name = str((config.get("deviceDetails") or {}).get("name") or "").strip()
    if name:
        return name
    try:
        return socket.gethostname().split(".")[0] or "zeroCAM"
    except Exception:
        return "zeroCAM"


def publish(config, logger):
    """
    Riscrive l'annuncio, se è cambiato.

    Il confronto con quanto già scritto evita di toccare il file a ogni
    salvataggio della configurazione: ogni scrittura fa ricaricare Avahi,
    e ricaricare significa ritirare e riannunciare il servizio, che per
    qualche istante sparisce dagli elenchi di chi sta guardando.

    Un fallimento non è grave e non deve fermare nulla: l'hostname resta
    annunciato comunque, ed è quello che si digita per raggiungere la
    webcam. Se ne prende nota nel log e si va avanti.
    """
    settings = config.get("settingsManager") or {}
    if not settings.get("http_enabled", True):
        # L'annuncio dice _http._tcp: senza HTTP prometterebbe una porta
        # che non risponde. In HTTPS il nome si digita a mano.
        _remove(logger)
        return False

    port = settings.get("port", 8080)
    content = TEMPLATE.format(name=escape(service_name(config)), port=int(port))

    try:
        if os.path.exists(SERVICE_FILE):
            with open(SERVICE_FILE, "r", encoding="utf-8") as f:
                if f.read() == content:
                    return False

        with open(SERVICE_FILE, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info(f"Announced the web interface on mDNS as '{service_name(config)}'.")
        return True
    except OSError as e:
        # Tipicamente il file non esiste ancora e la cartella è di root:
        # succede su un'installazione aggiornata da una versione che non
        # lo creava.
        logger.warning(f"Could not write the mDNS announcement ({SERVICE_FILE}): {e}")
        return False


def _remove(logger):
    """Toglie l'annuncio quando non c'è più un HTTP da annunciare."""
    try:
        if os.path.exists(SERVICE_FILE):
            os.remove(SERVICE_FILE)
            logger.info("Removed the mDNS announcement: HTTP is disabled.")
    except OSError as e:
        logger.warning(f"Could not remove the mDNS announcement: {e}")
