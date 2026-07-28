# -*- coding: utf-8 -*-
"""Riferimenti, nomi e limiti del materiale caricato dall'utente."""

import io
import os

import pytest
from PIL import Image

from lib import assets


class FakeUpload:
    """Espone il solo metodo che assets.save usa, come FileStorage."""

    def __init__(self, data=b"x"):
        self.data = data

    def save(self, target):
        with open(target, "wb") as f:
            f.write(self.data)


def png_bytes():
    buffer = io.BytesIO()
    Image.new("RGBA", (8, 8), (0, 128, 0, 255)).save(buffer, format="PNG")
    return buffer.getvalue()


def test_riferimento_e_scomposizione():
    reference = assets.reference("audio", "brano.mp3")
    assert reference == "asset:audio/brano.mp3"
    assert assets.parse(reference) == ("audio", "brano.mp3")


@pytest.mark.parametrize("value", [
    "",
    None,
    "https://esempio.it/logo.png",       # un URL resta un URL
    "/percorso/assoluto.png",
    "asset:inventata/x.png",             # categoria che non esiste
    "asset:audio/",                      # nome mancante
])
def test_valori_che_non_sono_riferimenti(value):
    assert assets.parse(value) is None


def test_il_riferimento_non_esce_dalla_cartella():
    """Un '..' scritto a mano in configurazione non deve risalire."""
    assert assets.parse("asset:audio/../../.conf.json") == ("audio", ".conf.json")
    assert assets.path("asset:audio/../../.conf.json") is None


def test_nome_ripulito():
    # Il nome finisce in una riga di comando di ffmpeg: niente spazi,
    # accenti o parentesi.
    assert assets.safe_name("Brano Estivo (2026).MP3") == "Brano-Estivo-2026-.MP3"
    assert assets.safe_name("città.png") == "citta.png"
    with pytest.raises(assets.AssetError):
        assets.safe_name("   ")


def test_estensioni_ammesse():
    assets.check_extension("audio", "brano.mp3")
    assets.check_extension("logo", "stemma.PNG")
    with pytest.raises(assets.AssetError):
        assets.check_extension("audio", "script.sh")
    with pytest.raises(assets.AssetError):
        assets.check_extension("logo", "brano.mp3")


def test_salvataggio_elenco_e_cancellazione():
    item = assets.save("logo", "Logo Città (2026).PNG", FakeUpload(png_bytes()))
    assert item["name"] == "Logo-Citta-2026-.PNG"
    assert item["reference"] == "asset:logo/Logo-Citta-2026-.PNG"
    assert item["size"] > 0

    nomi = [a["name"] for a in assets.listing("logo")]
    assert item["name"] in nomi
    assert assets.path(item["reference"]) is not None

    assert assets.delete("logo", item["name"]) is True
    assert assets.delete("logo", item["name"]) is False
    assert assets.path(item["reference"]) is None


def test_file_vuoto_rifiutato():
    with pytest.raises(assets.AssetError):
        assets.save("audio", "vuoto.mp3", FakeUpload(b""))
    assert assets.path("asset:audio/vuoto.mp3") is None


def test_categoria_sconosciuta():
    with pytest.raises(assets.AssetError):
        assets.save("script", "x.sh", FakeUpload())
    with pytest.raises(assets.AssetError):
        assets.listing("script")


def test_cancellazione_non_risale_le_cartelle(tmp_path):
    """delete prende il nome di base: '../..' non porta da nessuna parte."""
    assert assets.delete("logo", "../../.conf.json") is False


def test_url_locale_per_i_loghi():
    item = assets.save("logo", "stemma.png", FakeUpload(png_bytes()))
    url = assets.resolve_url(item["reference"])
    assert url.startswith("file://")
    assert os.path.isfile(url[len("file://"):])
    # Gli URL http configurati prima degli assets continuano a valere
    assert assets.resolve_url("https://esempio.it/x.png") == "https://esempio.it/x.png"
    assets.delete("logo", item["name"])


def test_asset_mancante_non_solleva():
    """Un riferimento rimasto in configurazione dopo la cancellazione."""
    assert assets.path("asset:audio/sparito.mp3") is None
    assert assets.resolve_url("asset:audio/sparito.mp3") == "asset:audio/sparito.mp3"
