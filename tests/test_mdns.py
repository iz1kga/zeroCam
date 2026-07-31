# -*- coding: utf-8 -*-
"""
Test dell'annuncio del servizio su mDNS.

Il file vero sta in /etc/avahi/services, dove i test non devono scrivere:
il percorso e' sovrascrivibile, e qui punta a una cartella temporanea.
"""

import pytest

from lib import mdns


@pytest.fixture
def annuncio(tmp_path, monkeypatch):
    percorso = tmp_path / "zerocam.service"
    monkeypatch.setattr(mdns, "SERVICE_FILE", str(percorso))
    return percorso


def configurazione(nome="Villar Focchiardo", porta=8080, http=True):
    return {
        "deviceDetails": {"name": nome},
        "settingsManager": {"port": porta, "http_enabled": http},
    }


def test_lannuncio_porta_il_nome_del_dispositivo(annuncio, logger):
    mdns.publish(configurazione(), logger)

    contenuto = annuncio.read_text(encoding="utf-8")
    assert "<name>Villar Focchiardo</name>" in contenuto
    assert "<port>8080</port>" in contenuto
    assert "_http._tcp" in contenuto


def test_un_nome_con_caratteri_speciali_non_rompe_lxml(annuncio, logger):
    # Avahi rifiuterebbe l'intero file, e il servizio sparirebbe dagli
    # elenchi senza che nulla lo segnali.
    mdns.publish(configurazione(nome='Baita "Alta" & Co. <test>'), logger)

    contenuto = annuncio.read_text(encoding="utf-8")
    assert "&amp;" in contenuto and "&lt;test&gt;" in contenuto

    import xml.etree.ElementTree as ET
    ET.fromstring(contenuto)  # deve restare XML valido


def test_senza_nome_si_ripiega_sullhostname(annuncio, logger, monkeypatch):
    monkeypatch.setattr(mdns.socket, "gethostname", lambda: "zerocam-a1b2")

    mdns.publish(configurazione(nome="   "), logger)

    assert "<name>zerocam-a1b2</name>" in annuncio.read_text(encoding="utf-8")


def test_riscrivere_lo_stesso_annuncio_non_tocca_il_file(annuncio, logger):
    assert mdns.publish(configurazione(), logger) is True
    # Ogni scrittura fa ricaricare Avahi, e ricaricare significa far
    # sparire il servizio dagli elenchi per un istante: senza il confronto
    # succederebbe a ogni salvataggio della configurazione.
    assert mdns.publish(configurazione(), logger) is False


def test_un_nome_cambiato_riscrive_lannuncio(annuncio, logger):
    mdns.publish(configurazione(), logger)
    assert mdns.publish(configurazione(nome="Lago di Avigliana"), logger) is True
    assert "Lago di Avigliana" in annuncio.read_text(encoding="utf-8")


def test_spegnendo_http_lannuncio_sparisce(annuncio, logger):
    mdns.publish(configurazione(), logger)
    assert annuncio.exists()

    # L'annuncio dice _http._tcp: senza HTTP prometterebbe una porta che
    # non risponde.
    mdns.publish(configurazione(http=False), logger)
    assert not annuncio.exists()


def test_un_file_non_scrivibile_non_ferma_lavvio(tmp_path, logger, monkeypatch):
    # Su un'installazione aggiornata da una versione che non lo creava, il
    # file non c'e' e la cartella e' di root. L'hostname resta annunciato
    # comunque, che e' quello che si digita: non c'e' motivo di fermarsi.
    monkeypatch.setattr(mdns, "SERVICE_FILE", str(tmp_path / "manca" / "zerocam.service"))

    assert mdns.publish(configurazione(), logger) is False
