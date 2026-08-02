# -*- coding: utf-8 -*-
"""
Test dell'immagine base per l'anteprima di annotazione e loghi.

L'anteprima vera si disegna nel browser e non si prova da qui. Quello che
si verifica e' il pezzo che sta sul dispositivo: conservare lo scatto
com'era prima di annotarlo, senza disturbare il buffer che deve proseguire
verso la pubblicazione.
"""

import io

import pytest
from PIL import Image

from lib import helpers


@pytest.fixture
def base(tmp_path, monkeypatch):
    percorso = tmp_path / "latest_base.jpg"
    monkeypatch.setattr(helpers, "STILL_BASE", str(percorso))
    return percorso


def scatto(size=(640, 480), colore=(120, 30, 30)):
    buffer = io.BytesIO()
    Image.new("RGB", size, colore).save(buffer, format="JPEG")
    buffer.seek(0)
    return buffer


def test_la_base_viene_conservata_come_immagine_valida(base, logger):
    helpers.saveStillBase(logger, scatto(size=(800, 600)))

    assert base.exists()
    with Image.open(base) as immagine:
        assert immagine.size == (800, 600)


def test_il_buffer_torna_dove_lo_abbiamo_trovato(base, logger):
    # Lo stesso buffer prosegue verso annotazione, EXIF e upload: lasciarlo
    # spostato significherebbe pubblicare un file troncato.
    buffer = scatto()
    buffer.seek(10)

    helpers.saveStillBase(logger, buffer)

    assert buffer.tell() == 10


def test_la_base_non_dipende_dalla_posizione_del_buffer(base, logger):
    # Chi chiama non garantisce di essere all'inizio: leggere da dove
    # capita darebbe un JPEG mozzato o nessun file.
    buffer = scatto(size=(320, 240))
    buffer.seek(50)

    helpers.saveStillBase(logger, buffer)

    with Image.open(base) as immagine:
        assert immagine.size == (320, 240)


def test_un_errore_di_scrittura_non_ferma_la_cattura(tmp_path, monkeypatch, logger):
    # E' una comodita' dell'interfaccia, non un pezzo della pubblicazione:
    # con il tmpfs pieno o assente lo scatto deve proseguire lo stesso.
    monkeypatch.setattr(helpers, "STILL_BASE", str(tmp_path / "manca" / "base.jpg"))
    buffer = scatto()

    helpers.saveStillBase(logger, buffer)

    assert buffer.tell() == 0, "il buffer resta utilizzabile anche quando fallisce"
