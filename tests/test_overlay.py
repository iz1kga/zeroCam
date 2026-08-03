# -*- coding: utf-8 -*-
"""
Test dei loghi sovrapposti.

L'elenco lo compone l'utente dall'interfaccia, quindi puo' contenere voci
appena create e ancora incomplete. Il ciclo di scatto non deve accorgersene:
un logo senza indirizzo e' una configurazione a meta', non un guasto.

Due accorgimenti, imparati scrivendo questi test a vuoto la prima volta.
Il confronto fra colori va fatto con una tolleranza, perche' il risultato
passa da un JPEG e il rosso pieno torna indietro leggermente diverso: un
`!= (255, 0, 0)` sarebbe vero anche quando il logo c'e'. E le guardie sul
contenuto incompleto non si vedono nell'immagine, perche' `add_overlays`
cattura ogni eccezione e prosegue: la differenza fra "saltato di proposito"
e "fallito" sta nel livello con cui la cosa finisce nel log.
"""

import io

import pytest
from PIL import Image

from lib.helpers import ImageOverlay

SFONDO = (20, 60, 120)
ROSSO = (255, 0, 0)


class LoggerFinto:
    """Registra i messaggi per livello, invece di stamparli."""

    def __init__(self):
        self.messaggi = {"info": [], "warning": [], "error": []}

    def info(self, message, *a, **k): self.messaggi["info"].append(str(message))

    def warning(self, message, *a, **k): self.messaggi["warning"].append(str(message))

    def error(self, message, *a, **k): self.messaggi["error"].append(str(message))

    def debug(self, message, *a, **k): pass

    @property
    def errori(self):
        return self.messaggi["error"]


def scatto(size=(400, 300)):
    buffer = io.BytesIO()
    Image.new("RGB", size, SFONDO).save(buffer, format="JPEG")
    buffer.seek(0)
    return buffer


def logo(**campi):
    voce = {"enabled": True, "name": "Logo", "url": "", "X": 0, "Y": 0,
            "scale": 100, "opacity": 100}
    voce.update(campi)
    return voce


def vicino(pixel, atteso, tolleranza=20):
    """Confronto fra colori che sopravvive alla compressione JPEG."""
    return all(abs(a - b) <= tolleranza for a, b in zip(pixel, atteso))


def pixel(buffer, punto=(10, 10)):
    with Image.open(buffer) as immagine:
        return immagine.convert("RGB").getpixel(punto)


@pytest.fixture
def registro():
    return LoggerFinto()


@pytest.fixture
def caricato(registro):
    """Un overlay con l'immagine gia' in memoria, senza scaricare nulla."""
    def costruisci(voci, immagine=None):
        overlay = ImageOverlay([], registro)
        overlay.OverlayImages = [dict(v) for v in voci]
        for voce in overlay.OverlayImages:
            if voce.get("url"):
                voce["image"] = immagine or Image.new("RGBA", (400, 300), ROSSO + (255,))
        return overlay
    return costruisci


def test_un_logo_senza_indirizzo_non_e_un_errore(registro):
    # E' quello che si ottiene premendo 'Aggiungi' e non scegliendo ancora
    # il file. Senza la guardia, ogni salvataggio della configurazione
    # finirebbe nel log come errore di scaricamento.
    ImageOverlay([logo(url="")], registro)

    assert registro.errori == []
    assert any("has no image yet" in m for m in registro.messaggi["info"])


def test_un_logo_senza_immagine_viene_saltato_senza_errori(caricato, registro):
    overlay = caricato([logo(url="")])

    risultato = overlay.add_overlays(scatto())

    assert registro.errori == [], "un logo incompleto non e' un guasto"
    assert vicino(pixel(risultato), SFONDO), "lo scatto prosegue intatto"


def test_le_chiavi_mancanti_valgono_i_default(caricato, registro):
    # Una voce scritta a mano in .conf.json puo' non avere tutti i campi:
    # devono valere i default, non un'eccezione che salta il logo.
    overlay = caricato([{"enabled": True, "url": "asset:logo/x.png"}])

    risultato = overlay.add_overlays(scatto())

    assert registro.errori == []
    assert vicino(pixel(risultato), ROSSO), "incollato con X, Y e scala di default"


def test_un_elenco_vuoto_restituisce_lo_scatto(caricato, registro):
    # E' il default di un'installazione nuova.
    overlay = caricato([])

    risultato = overlay.add_overlays(scatto())

    assert registro.errori == []
    assert vicino(pixel(risultato), SFONDO)


def test_un_logo_spento_non_viene_incollato(caricato):
    overlay = caricato([logo(url="asset:logo/x.png", enabled=False)])

    risultato = overlay.add_overlays(scatto())

    assert vicino(pixel(risultato), SFONDO)


def test_un_logo_acceso_finisce_sullo_scatto(caricato):
    overlay = caricato([logo(url="asset:logo/x.png")])

    risultato = overlay.add_overlays(scatto())

    assert vicino(pixel(risultato), ROSSO)
