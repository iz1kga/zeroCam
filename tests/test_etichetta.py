# -*- coding: utf-8 -*-
"""
Test dell'etichetta del dispositivo.

Quello che conta e' la stringa del QR della rete: se e' malformata il
telefono legge una rete che non esiste, e chi ha in mano la webcam non ha
nessun altro modo per entrarci. Il disegno invece si guarda, non si
verifica: qui basta che esca un'immagine e non un'eccezione.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "installation_tools"))

import genera_etichetta as etichetta  # noqa: E402


def test_la_rete_finisce_nel_formato_che_i_telefoni_leggono():
    assert (etichetta.wifi_payload("zeroCAM-a1b2", "hw3xpukcty")
            == "WIFI:S:zeroCAM-a1b2;T:WPA;P:hw3xpukcty;;")


@pytest.mark.parametrize("carattere", ["\\", ";", ",", ":", '"'])
def test_i_caratteri_riservati_vengono_protetti(carattere):
    # Non protetti chiuderebbero il campo in anticipo: il telefono
    # leggerebbe un nome troncato e proverebbe a collegarsi a una rete
    # che non esiste, senza che nulla lo segnali.
    payload = etichetta.wifi_payload(f"rete{carattere}strana", "unapassword")

    assert f"\\{carattere}" in payload
    # Il numero di separatori deve restare quello di un payload sano.
    assert payload.count(";") - payload.count("\\;") == 4


def test_una_rete_nascosta_lo_dichiara():
    assert "H:true;" in etichetta.wifi_payload("Nascosta", "unapassword", hidden=True)
    assert "H:true;" not in etichetta.wifi_payload("Visibile", "unapassword")


def test_letichetta_viene_disegnata(tmp_path):
    immagine = etichetta.build("zerocam-a1b2", "zeroCAM-a1b2", "hw3xpukcty")

    assert immagine.size == (etichetta.WIDTH, etichetta.HEIGHT)
    percorso = tmp_path / "etichetta.png"
    immagine.save(percorso)
    assert percorso.stat().st_size > 0


def test_un_nome_lungo_non_fa_saltare_il_disegno():
    # Un hostname imposto a mano puo' essere lungo quanto si vuole: deve
    # uscire un'etichetta comunque, anche se stretta.
    etichetta.build("webcam-lago-di-avigliana-versante-nord",
                    "zeroCAM-webcam-lago-di-avigliana-versante-nord", "hw3xpukcty")
