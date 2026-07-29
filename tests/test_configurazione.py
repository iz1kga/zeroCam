# -*- coding: utf-8 -*-
"""
Valori di default e pianificazione.

Le chiavi nuove devono comparire da sole nelle installazioni esistenti,
senza sovrascrivere quello che l'utente ha gia' scelto: e' il meccanismo
che rende indolori gli aggiornamenti.
"""

import json
import threading
import types

import schedule

from lib.components.config_manager import DEFAULT_SECTIONS, ConfigManager
from lib.components.scheduler_manager import SchedulerManager


def carica(tmp_path, contenuto, logger):
    percorso = tmp_path / "conf.json"
    percorso.write_text(json.dumps(contenuto))
    return ConfigManager(logger, "chiave-di-prova", config_path=str(percorso))


def test_le_sezioni_nuove_compaiono(tmp_path, logger):
    manager = carica(tmp_path, {"deviceDetails": {"name": "webcam"}}, logger)
    for sezione in DEFAULT_SECTIONS:
        assert sezione in manager.config, sezione
    assert manager.config["timelapse"]["retention_weeks"] == 4
    assert manager.config["settingsManager"]["https_port"] == 8443
    assert manager.config["settingsManager"]["public_page"] is False


def test_i_valori_dell_utente_non_vengono_toccati(tmp_path, logger):
    manager = carica(tmp_path, {
        "timelapse": {"enabled": True, "retention_weeks": 12},
        "settingsManager": {"port": 9090},
    }, logger)
    assert manager.config["timelapse"]["retention_weeks"] == 12
    assert manager.config["settingsManager"]["port"] == 9090
    # e nel frattempo le chiavi mancanti sono state aggiunte
    assert manager.config["timelapse"]["audio_volume"] == 100
    assert manager.config["settingsManager"]["https_enabled"] is False


def test_ftp_acceso_per_chi_lo_usava_gia(tmp_path, logger):
    """L'interruttore e' arrivato dopo: chi aveva l'FTP configurato lo vuole acceso."""
    manager = carica(tmp_path, {"FtpHost": {"host": "upload.esempio.it"}}, logger)
    assert manager.config["FtpHost"]["enabled"] is True


def pianificatore(logger, conf):
    app = types.SimpleNamespace(
        shutdown_flag=threading.Event(),
        capture_active=threading.Event(),
        config_manager=types.SimpleNamespace(get=lambda k, d=None: conf.get(k, d)),
        publish_diagnostic=lambda *a: None,
        stats_collector=types.SimpleNamespace(collect_and_process=lambda: None),
        components=types.SimpleNamespace(
            timelapse=types.SimpleNamespace(cleanup_old_frames=lambda: None)),
        capture_job=lambda: None,
    )
    return SchedulerManager(app, logger)


def test_la_pianificazione_si_rifa_solo_quando_serve(logger):
    """Rifarla azzera i conteggi: un salvataggio qualsiasi rimanderebbe lo scatto."""
    schedule.clear()
    conf = {"cameraParameters": {"shotInterval": 600},
            "timelapse": {"enabled": True, "day": "monday", "time": "03:00"}}
    manager = pianificatore(logger, conf)
    manager.setup_jobs()
    iniziali = len(schedule.jobs)

    assert manager.reload_jobs() is False
    assert len(schedule.jobs) == iniziali

    conf["cameraParameters"]["shotInterval"] = 300
    assert manager.reload_jobs() is True
    assert len(schedule.jobs) == iniziali, "i job non si accumulano a ogni ricostruzione"

    conf["timelapse"]["enabled"] = False
    assert manager.reload_jobs() is True
    assert len(schedule.jobs) == iniziali - 2, "sparisce il montaggio e la pulizia"

    conf["timelapse"].update(enabled=True, day="thursday", time="05:15")
    assert manager.reload_jobs() is True
    assert len(schedule.jobs) == iniziali
    schedule.clear()
