# -*- coding: utf-8 -*-
"""Riuso e ricambio giornaliero della diretta."""

from datetime import datetime, timedelta, timezone

import pytest

from lib.youtube_live import YouTubeLiveManager, _parse_hhmm, _parse_iso


def manager(logger, reset_time):
    return YouTubeLiveManager({"daily_reset_time": reset_time}, "chiave", logger, auth=object())


def broadcast(ore_fa, lifecycle="live"):
    started = datetime.now(timezone.utc) - timedelta(hours=ore_fa)
    return {"id": "Ab12", "status": {"lifeCycleStatus": lifecycle},
            "snippet": {"actualStartTime": started.strftime("%Y-%m-%dT%H:%M:%SZ")}}


@pytest.mark.parametrize("value,atteso", [
    ("00:00", (0, 0)), ("4:30", (4, 30)), ("23:59", (23, 59)),
])
def test_orari_validi(value, atteso):
    parsed = _parse_hhmm(value)
    assert (parsed.hour, parsed.minute) == atteso


@pytest.mark.parametrize("value", ["", None, "  ", "25:70", "mezzanotte", "12", "12:60"])
def test_orari_non_validi(value):
    assert _parse_hhmm(value) is None


def test_timestamp_di_youtube():
    assert _parse_iso("2026-07-28T00:15:00Z").tzinfo is not None
    assert _parse_iso("") is None
    assert _parse_iso("ieri") is None


def test_senza_reset_la_diretta_si_riusa_sempre(logger):
    yt = manager(logger, "")
    assert yt._rollover_boundary() is None
    assert yt._is_stale(broadcast(ore_fa=50)) is False
    assert "not configured" in yt._rollover_note()


def test_orario_malformato_non_ricambia_di_nascosto(logger):
    """Disattivare in silenzio sarebbe indistinguibile da un guasto."""
    yt = manager(logger, "25:70")
    assert yt._is_stale(broadcast(ore_fa=50)) is False
    assert "not a valid HH:MM" in yt._rollover_note()


def test_diretta_piu_vecchia_del_confine(logger):
    yt = manager(logger, "00:00")
    # Una diretta di due giorni fa e' per forza precedente all'ultima mezzanotte
    assert yt._is_stale(broadcast(ore_fa=48)) is True


def test_diretta_piu_recente_del_confine(logger):
    yt = manager(logger, "00:00")
    assert yt._is_stale(broadcast(ore_fa=0)) is False
    assert "started after the daily reset" in yt._rollover_note()


def test_senza_data_di_avvio_si_riusa(logger):
    """Senza una data affidabile ricreare a ogni scatto sarebbe peggio."""
    yt = manager(logger, "00:00")
    assert yt._is_stale({"id": "Ab12", "snippet": {}}) is False


def test_il_confine_e_nel_passato(logger):
    yt = manager(logger, "23:59")
    boundary = yt._rollover_boundary()
    assert boundary is not None
    assert boundary <= datetime.now().astimezone()
    assert (datetime.now().astimezone() - boundary) < timedelta(days=1)
