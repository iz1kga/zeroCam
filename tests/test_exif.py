# -*- coding: utf-8 -*-
"""Metadati riscritti negli scatti."""

import io
import json
from datetime import datetime

import piexif
from PIL import Image
from piexif import helper

from lib import exif


def jpeg():
    buffer = io.BytesIO()
    Image.new("RGB", (64, 48), (20, 40, 60)).save(buffer, format="JPEG")
    buffer.seek(0)
    return buffer


def test_campi_standard(metadata):
    blob = exif.build(metadata, datetime(2026, 7, 28, 1, 39, 29), description="Villar - night")
    data = piexif.load(blob)

    assert data["0th"][piexif.ImageIFD.DateTime] == b"2026:07:28 01:39:29"
    assert data["Exif"][piexif.ExifIFD.DateTimeOriginal] == b"2026:07:28 01:39:29"
    # ExposureTime di libcamera e' in microsecondi
    assert data["Exif"][piexif.ExifIFD.ExposureTime] == (33234, 1000000)
    # ISO ricavato dal guadagno analogico
    assert data["Exif"][piexif.ExifIFD.ISOSpeedRatings] == 800
    assert data["Exif"][piexif.ExifIFD.WhiteBalance] == 0


def test_bilanciamento_manuale_dichiarato(metadata):
    blob = exif.build(metadata, datetime.now(), manual_white_balance=True)
    assert piexif.load(blob)["Exif"][piexif.ExifIFD.WhiteBalance] == 1


def test_commento_leggibile_e_completo(metadata):
    """I guadagni sono il motivo per cui questi metadati esistono."""
    blob = exif.build(metadata, datetime.now())
    raw = piexif.load(blob)["Exif"][piexif.ExifIFD.UserComment]

    # ASCII e non UCS-2: i visualizzatori dichiarano l'altra non supportata
    assert raw[:8] == b"ASCII\x00\x00\x00"
    payload = json.loads(helper.UserComment.load(raw))
    assert payload["ColourGains"] == [2.31, 1.47]
    assert payload["ColourTemperature"] == 3100
    assert payload["Lux"] == 12.7


def test_descrizione_riassuntiva(metadata):
    blob = exif.build(metadata, datetime.now(), description="Villar - night")
    descrizione = piexif.load(blob)["0th"][piexif.ImageIFD.ImageDescription].decode()
    assert descrizione.startswith("Villar - night")
    # Deve leggersi anche in un visualizzatore che ignora il commento
    assert "ColourGains R=2.31 B=1.47" in descrizione
    assert "3100K" in descrizione


def test_riassunto_con_metadati_parziali():
    assert exif.summary({}) == ""
    assert "exp 500us" in exif.summary({"ExposureTime": 500})


def test_inserimento_nel_buffer(metadata):
    buffer = jpeg()
    prima = len(buffer.getvalue())
    updated = exif.attach(buffer, metadata, datetime.now(), description="Villar - day")

    dati = updated.getvalue()
    assert len(dati) > prima
    assert updated.tell() == 0, "il buffer torna a chi lo legge gia' riavvolto"
    payload = json.loads(helper.UserComment.load(
        piexif.load(dati)["Exif"][piexif.ExifIFD.UserComment]))
    assert payload["ColourGains"] == [2.31, 1.47]


def test_un_buffer_non_jpeg_non_fa_perdere_lo_scatto(metadata):
    rotto = io.BytesIO(b"non sono un jpeg")
    assert exif.attach(rotto, metadata, datetime.now()).read() == b"non sono un jpeg"


def test_metadati_assenti(metadata):
    blob = exif.build({}, datetime.now())
    assert blob, "restano data e provenienza anche senza metadati di scatto"
    assert piexif.ExifIFD.ExposureTime not in piexif.load(blob)["Exif"]


def test_valori_non_serializzabili_scartati():
    """La configurazione deve restare convertibile in JSON."""
    blob = exif.build({"Strano": object(), "ColourGains": (1.0, 2.0)}, datetime.now())
    payload = json.loads(helper.UserComment.load(
        piexif.load(blob)["Exif"][piexif.ExifIFD.UserComment]))
    assert "Strano" not in payload
    assert payload["ColourGains"] == [1.0, 2.0]
