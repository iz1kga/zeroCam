# -*- coding: utf-8 -*-
"""
Destinazioni degli scatti e vetrina pubblica.

Il punto delicato e' uno: la pagina pubblica non chiede autenticazione,
quindi non deve lasciar uscire nulla oltre all'immagine.
"""

import logging
import os
import types

import pytest
from flask import Flask

import settingsManager as sm
from lib import paths
from lib.helpers import FTPUploader, HttpUploader
from lib.timelapse import TimelapseManager


# --- Upload FTP ------------------------------------------------------

class FTPFinto:
    tentativi = 0


def test_ftp_spento_non_tenta_il_collegamento(logger, monkeypatch):
    tentato = []
    monkeypatch.setattr("lib.helpers.FTP", lambda *a, **k: tentato.append(True))

    uploader = FTPUploader({"enabled": False, "host": "upload.esempio.it"}, logger)
    uploader.upload(b"immagine", {})
    assert tentato == [], "spento vuol dire che non deve nemmeno provarci"


def test_ftp_acceso_ci_prova(logger, monkeypatch):
    tentato = []

    class Finto:
        def connect(self, *a, **k): tentato.append("connect")
        def login(self, *a, **k): pass
        def cwd(self, *a): pass
        def set_pasv(self, *a): pass
        def storbinary(self, *a): tentato.append("store")
        def quit(self): pass

    monkeypatch.setattr("lib.helpers.FTP", Finto)
    uploader = FTPUploader({"enabled": True, "host": "upload.esempio.it", "port": 21,
                            "timeout": 30, "username": "u", "password": "p",
                            "folder": "/", "filename": "webcam.jpg"}, logger)
    uploader.upload(b"immagine", {})
    assert tentato == ["connect", "store"]


def test_ftp_senza_chiave_resta_acceso(logger, monkeypatch):
    """Le configurazioni scritte prima dell'interruttore non devono spegnersi."""
    tentato = []
    monkeypatch.setattr("lib.helpers.FTP", lambda *a, **k: tentato.append(True) or (_ for _ in ()).throw(OSError()))
    FTPUploader({"host": "upload.esempio.it"}, logger).upload(b"x", {})
    assert tentato, "senza la chiave 'enabled' il comportamento resta quello di prima"


def test_http_spento(logger, monkeypatch):
    chiamate = []
    monkeypatch.setattr("lib.helpers.requests.post", lambda *a, **k: chiamate.append(True))
    HttpUploader({"enabled": False, "url": "https://esempio.it"}, logger).upload(b"x", {})
    assert chiamate == []


# --- Audio del timelapse ---------------------------------------------

def test_timelapse_muto_senza_brano(logger):
    manager = TimelapseManager.__new__(TimelapseManager)
    manager.logger, manager.cfg = logger, {}
    assert manager._audio_arguments() == []


def test_timelapse_con_brano_mancante_resta_muto(logger):
    manager = TimelapseManager.__new__(TimelapseManager)
    manager.logger, manager.cfg = logger, {"audio_file": "asset:audio/sparito.mp3"}
    assert manager._audio_arguments() == []


# --- Pagina pubblica -------------------------------------------------

@pytest.fixture
def vetrina(tmp_path):
    conf = {
        "settingsManager": {"public_page": True, "public_title": "",
                            "public_live_url": "https://youtu.be/esempio"},
        "deviceDetails": {"name": "Villar Focchiardo"},
        "cameraParameters": {"shotInterval": 600},
        "security": {"password": "hash-segretissimo"},
        "streamParameters": {"yt_api_key": "chiave-di-streaming"},
    }
    manager = sm.SettingsManager.__new__(sm.SettingsManager)
    manager.logger = logging.getLogger("zerocam-tests")
    manager.zerocam = types.SimpleNamespace(
        config_manager=types.SimpleNamespace(get=lambda k, d=None: conf.get(k, d)))

    app = Flask(__name__,
                template_folder=os.path.join(os.path.dirname(os.path.dirname(
                    os.path.abspath(__file__))), "templates"),
                static_folder="static")
    app.add_url_rule("/public/latest.jpg", "public_image", lambda: None)
    app.add_url_rule("/public/info", "public_info", lambda: None)
    # La vetrina rimanda alla console col lucchetto: la rotta deve esistere
    app.add_url_rule("/zc-admin", "index", lambda: None)

    os.makedirs(paths.DATA_DIR, exist_ok=True)
    with open(paths.LATEST_IMAGE, "wb") as f:
        f.write(b"\xff\xd8jpeg-finto")

    return manager, app, conf


def test_vetrina_spenta_non_risponde(vetrina):
    manager, app, conf = vetrina
    conf["settingsManager"]["public_page"] = False
    with app.test_request_context("/public"):
        assert manager.public_page()[1] == 404
        assert manager.public_image()[1] == 404
        assert manager.public_info()[1] == 404


def test_vetrina_accesa_mostra_lo_scatto(vetrina):
    manager, app, _ = vetrina
    with app.test_request_context("/public"):
        html = manager.public_page()
        assert "Villar Focchiardo" in html
        assert "youtu.be/esempio" in html
        assert manager.public_image().status_code == 200
        assert manager.public_info().get_json()["captured_at"] > 0


def test_la_vetrina_non_lascia_uscire_altro(vetrina):
    """Senza autenticazione davanti, tutto quello che c'e' e' pubblico."""
    manager, app, _ = vetrina
    with app.test_request_context("/public"):
        html = manager.public_page()
    for segreto in ("hash-segretissimo", "chiave-di-streaming", "password",
                    "client_secret", "refresh_token"):
        assert segreto not in html, segreto
    # e nemmeno un aggancio alla console
    assert "/api/config" not in html
    assert "Configuration" not in html


def test_la_radice_mostra_la_vetrina_quando_e_accesa(vetrina, monkeypatch):
    manager, app, conf = vetrina
    chiamate = []
    monkeypatch.setattr(sm.SettingsManager, "index",
                        lambda self: chiamate.append("console") or "console")

    with app.test_request_context("/"):
        assert "Villar Focchiardo" in manager.root()
    assert chiamate == [], "la vetrina non deve passare dalla console"


def test_la_radice_resta_la_console_quando_e_spenta(vetrina, monkeypatch):
    """Chi non usa la vetrina non deve accorgersi di nulla."""
    manager, app, conf = vetrina
    conf["settingsManager"]["public_page"] = False
    monkeypatch.setattr(sm.SettingsManager, "index", lambda self: "console")

    with app.test_request_context("/"):
        assert manager.root() == "console"


@pytest.mark.parametrize("richiesto,atteso", [
    ("/zc-admin", "/zc-admin"),
    ("/api/config", "/api/config"),
    ("https://sito-cattivo.example/", None),   # un altro sito, no
    ("//sito-cattivo.example/", None),         # nemmeno senza schema
    ("", None),
    ("zc-admin", None),                        # non e' un percorso assoluto
])
def test_dopo_il_login_si_torna_solo_su_pagine_nostre(vetrina, richiesto, atteso):
    manager, app, _ = vetrina
    with app.test_request_context("/login", query_string={"next": richiesto}):
        assert manager._safe_next() == atteso


def test_titolo_personalizzato(vetrina):
    manager, app, conf = vetrina
    conf["settingsManager"]["public_title"] = "Panorama della Val Susa"
    with app.test_request_context("/public"):
        assert "Panorama della Val Susa" in manager.public_page()


def test_aggiornamento_legato_all_intervallo_di_scatto(vetrina):
    manager, app, conf = vetrina
    conf["cameraParameters"]["shotInterval"] = 600
    with app.test_request_context("/public"):
        assert "300 * 1000" in manager.public_page()

    # Un intervallo cortissimo non deve far martellare il dispositivo
    conf["cameraParameters"]["shotInterval"] = 10
    with app.test_request_context("/public"):
        assert "30 * 1000" in manager.public_page()
