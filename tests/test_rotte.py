# -*- coding: utf-8 -*-
"""
Smistamento delle rotte, sulla tabella vera dell'applicazione.

I test degli altri file chiamano i metodi uno per uno; qui si monta il
routing come lo monta il programma, perche' l'errore che conta - la
console raggiungibile senza autenticazione, o la vetrina che sparisce -
nasce dal modo in cui le rotte stanno insieme, non dai singoli metodi.
"""

import logging
import os
import types

import pytest
from flask import Flask

import settingsManager as sm
from lib import paths


@pytest.fixture
def app(tmp_path):
    conf = {
        "settingsManager": {"public_page": True, "public_title": "Vetrina",
                            "public_live_url": ""},
        "deviceDetails": {"name": "Villar Focchiardo"},
        "cameraParameters": {"shotInterval": 600},
        "security": {"username": "admin", "password": "hash", "flask_secret_key": "chiave"},
        "onvif": {"enabled": False},
    }
    manager = sm.SettingsManager.__new__(sm.SettingsManager)
    manager.logger = logging.getLogger("zerocam-tests")
    manager.zerocam = types.SimpleNamespace(
        config_manager=types.SimpleNamespace(
            get=lambda k, d=None: conf.get(k, d),
            get_raw=lambda k, d=None: conf.get(k, d)))

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    manager.app = Flask(__name__,
                        template_folder=os.path.join(root, "templates"),
                        static_folder=os.path.join(root, "static"))
    manager.app.config["SECRET_KEY"] = "chiave"
    manager._setup_login_manager()
    manager._register_routes()

    os.makedirs(paths.DATA_DIR, exist_ok=True)
    with open(paths.LATEST_IMAGE, "wb") as f:
        f.write(b"\xff\xd8jpeg-finto")

    return manager.app.test_client(), conf


def test_con_la_vetrina_accesa_la_radice_e_la_vetrina(app):
    client, _ = app
    risposta = client.get("/")
    assert risposta.status_code == 200
    assert b"Vetrina" in risposta.data
    assert b"/zc-admin" in risposta.data, "il lucchetto porta alla console"


def test_la_console_chiede_sempre_di_accedere(app):
    client, conf = app
    for accesa in (True, False):
        conf["settingsManager"]["public_page"] = accesa
        risposta = client.get("/zc-admin")
        assert risposta.status_code == 302
        assert "/login" in risposta.headers["Location"]


def test_con_la_vetrina_spenta_la_radice_torna_la_console(app):
    client, conf = app
    conf["settingsManager"]["public_page"] = False
    risposta = client.get("/")
    assert risposta.status_code == 302
    assert "/login" in risposta.headers["Location"]


def test_le_rotte_pubbliche_non_espongono_altro(app):
    """Tutto cio' che risponde senza sessione deve essere solo la vetrina."""
    client, _ = app
    for percorso in ("/api/config", "/api/log", "/api/stats", "/latest.jpg",
                     "/api/assets", "/api/timelapse"):
        risposta = client.get(percorso)
        assert risposta.status_code in (302, 401), f"{percorso} risponde {risposta.status_code}"

    for percorso in ("/", "/public", "/public/latest.jpg", "/public/info"):
        assert client.get(percorso).status_code == 200, percorso


def test_le_rotte_pubbliche_spariscono_quando_la_vetrina_e_spenta(app):
    client, conf = app
    conf["settingsManager"]["public_page"] = False
    for percorso in ("/public", "/public/latest.jpg", "/public/info"):
        assert client.get(percorso).status_code == 404, percorso
