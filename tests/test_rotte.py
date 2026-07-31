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
from lib import netwatch, paths


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

    client = manager.app.test_client()
    # I test della rete devono poter sostituire pezzi dell'applicazione
    # finta: il client e' l'unica cosa che ricevono.
    client.zerocam = manager.zerocam
    client.logger = manager.logger
    return client, conf


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
                     "/api/assets", "/api/timelapse",
                     "/api/network", "/api/network/scan"):
        risposta = client.get(percorso)
        assert risposta.status_code in (302, 401), f"{percorso} risponde {risposta.status_code}"

    for percorso in ("/", "/public", "/public/latest.jpg", "/public/info"):
        assert client.get(percorso).status_code == 200, percorso


def test_le_rotte_pubbliche_spariscono_quando_la_vetrina_e_spenta(app):
    client, conf = app
    conf["settingsManager"]["public_page"] = False
    for percorso in ("/public", "/public/latest.jpg", "/public/info"):
        assert client.get(percorso).status_code == 404, percorso


# --- Rete ---
#
# Le rotte di rete sono verificate qui e non in test_network.py perche' e'
# la traduzione fra richiesta HTTP e chiamata a nmcli che conta: il modulo
# sottostante ha gia' i suoi test, e viene sostituito da una finta.


class FakeNetwork:
    """Sta al posto di lib.network, registrando cosa gli viene chiesto."""

    # Riempito dalla fixture con l'eccezione vera: settingsManager la
    # nomina nei suoi except, e una finta non verrebbe intercettata.
    NetworkError = None

    def __init__(self):
        self.calls = []
        self.fail = None
        self.hotspot = False
        self.saved = [{"name": "CasaMia", "type": "802-11-wireless", "device": "wlan0"}]

    def _record(self, name, **kwargs):
        self.calls.append((name, kwargs))
        if self.fail == name:
            raise self.NetworkError("nmcli ha detto di no")

    def status(self):
        self._record("status")
        return {"available": True, "connectivity": "full", "hotspot": False,
                "devices": [{"device": "eth0", "connection": "Wired connection 1"}]}

    def saved_wifi(self):
        self._record("saved_wifi")
        return list(self.saved)

    def wifi_device(self):
        self._record("wifi_device")
        return "wlan0"

    def scan(self):
        self._record("scan")
        return [{"ssid": "CasaMia", "signal": 80, "security": "WPA2", "open": False,
                 "active": False}]

    def wifi_connect(self, ssid, password="", hidden=False):
        self._record("wifi_connect", ssid=ssid, password=password, hidden=hidden)
        return True

    def forget(self, name):
        self._record("forget", name=name)
        return True

    def set_static(self, connection, address, gateway="", dns=None):
        self._record("set_static", connection=connection, address=address,
                     gateway=gateway, dns=dns)
        return True

    def set_dhcp(self, connection):
        self._record("set_dhcp", connection=connection)
        return True

    def hotspot_active(self):
        return self.hotspot

    def hotspot_start(self, ssid, password, ifname="wlan0"):
        self._record("hotspot_start", ssid=ssid, password=password, ifname=ifname)
        self.hotspot = True
        return True

    def available(self):
        return True

    def connectivity(self):
        # Un hotspot acceso non porta da nessuna parte: e' la situazione in
        # cui il watchdog decide se valga la pena liberare la radio.
        return "none" if self.hotspot else "full"

    def hotspot_stop(self):
        self._record("hotspot_stop")
        self.hotspot = False
        return True

    def command(self, name):
        for called, kwargs in self.calls:
            if called == name:
                return kwargs
        return None


@pytest.fixture
def rete(app, monkeypatch):
    """
    Client gia' autenticato e nmcli sostituito.

    LOGIN_DISABLED e' il modo previsto da Flask-Login per provare le rotte
    protette: la sessione non e' quello che questi test verificano, e ci
    pensa gia' test_le_rotte_pubbliche_non_espongono_altro.
    """
    from lib import netwatch
    from lib import network as vero

    client, _ = app
    client.application.config["LOGIN_DISABLED"] = True

    finta = FakeNetwork()
    finta.NetworkError = vero.NetworkError
    monkeypatch.setattr(sm, "network", finta)
    # Il watchdog e' quello vero, ma guarda la stessa finta: le rotte lo
    # interrogano per lo stato dell'hotspot e per riaccenderlo.
    monkeypatch.setattr(netwatch, "network", finta)
    client.zerocam.netwatch = netwatch.NetworkWatchdog(
        {"hotspot_enabled": True, "hotspot_ssid": "zeroCAM-a1b2",
         "hotspot_password": "unapassword"}, client.logger)
    return client, finta


def test_lo_stato_di_rete_arriva_in_una_risposta_sola(rete):
    client, _ = rete
    dati = client.get("/api/network").get_json()

    # La pagina si aggiorna a intervalli: interfacce, reti salvate e nome
    # dell'interfaccia wifi devono viaggiare insieme o si mostrerebbero
    # disallineate fra loro.
    assert dati["available"] is True
    assert dati["saved"][0]["name"] == "CasaMia"
    assert dati["wifiDevice"] == "wlan0"


def test_la_pagina_di_rete_e_servibile(rete):
    # Il template arriva al browser da qui: se il nome non passa il
    # controllo della rotta, la voce di menu apre una pagina vuota.
    client, _ = rete
    risposta = client.get("/view/pages/network.html")

    assert risposta.status_code == 200
    assert b"Wi-Fi" in risposta.data


def test_senza_networkmanager_non_si_chiedono_le_reti_salvate(rete, monkeypatch):
    client, finta = rete
    monkeypatch.setattr(finta, "status", lambda: {
        "available": False, "connectivity": "unknown", "devices": [], "hotspot": False})

    dati = client.get("/api/network").get_json()

    assert dati["saved"] == []
    assert finta.command("saved_wifi") is None


def test_i_dns_arrivano_come_lista_ripulita(rete):
    client, finta = rete
    client.post("/api/network/address", json={
        "connection": "Wired connection 1", "method": "manual",
        "address": "192.168.1.50/24", "gateway": "192.168.1.1",
        "dns": ["8.8.8.8", "  ", " 1.1.1.1 "]})

    chiamata = finta.command("set_static")
    # Le righe vuote del textarea non devono diventare DNS inesistenti.
    assert chiamata["dns"] == ["8.8.8.8", "1.1.1.1"]
    assert chiamata["address"] == "192.168.1.50/24"


def test_il_metodo_automatico_non_porta_indirizzi_con_se(rete):
    client, finta = rete
    client.post("/api/network/address", json={
        "connection": "Wired connection 1", "method": "auto",
        "address": "192.168.1.50/24"})

    assert finta.command("set_dhcp") == {"connection": "Wired connection 1"}
    assert finta.command("set_static") is None


def test_senza_profilo_non_si_riconfigura_niente(rete):
    client, finta = rete
    risposta = client.post("/api/network/address", json={"method": "auto"})

    assert risposta.status_code == 400
    assert finta.command("set_dhcp") is None


def test_un_rifiuto_di_nmcli_diventa_un_400_col_suo_motivo(rete):
    client, finta = rete
    finta.fail = "wifi_connect"

    risposta = client.post("/api/network/wifi",
                           json={"ssid": "CasaMia", "password": "unapassword"})

    assert risposta.status_code == 400
    # Il motivo vero e' l'unica cosa che aiuta chi sta sbagliando password.
    assert "nmcli ha detto di no" in risposta.get_json()["message"]


def test_una_password_sbagliata_non_lascia_la_webcam_muta(rete):
    client, finta = rete
    # Chi configura e' collegato all'hotspot: connettersi a una rete lo
    # spegne, e se il tentativo fallisce resterebbe senza niente.
    finta.hotspot = True
    finta.fail = "wifi_connect"

    client.post("/api/network/wifi", json={"ssid": "CasaMia", "password": "sbagliata1"})

    riacceso = finta.command("hotspot_start")
    assert riacceso is not None, "senza questo il dispositivo resta irraggiungibile"
    assert riacceso["ssid"] == "zeroCAM-a1b2"


def test_senza_hotspot_un_fallimento_non_ne_accende_uno(rete):
    client, finta = rete
    finta.hotspot = False
    finta.fail = "wifi_connect"

    client.post("/api/network/wifi", json={"ssid": "CasaMia", "password": "sbagliata1"})

    # Chi sta configurando dal cavo non ha chiesto nessun access point.
    assert finta.command("hotspot_start") is None


def test_lo_stato_dellhotspot_arriva_alla_pagina(rete):
    client, finta = rete
    finta.hotspot = True

    dati = client.get("/api/network").get_json()

    assert dati["hotspotConfig"]["active"] is True
    assert dati["hotspotConfig"]["ssid"] == "zeroCAM-a1b2"
    # La password si stampa sull'etichetta, quindi va mostrata a chi ha
    # gia' l'accesso alla console.
    assert dati["hotspotConfig"]["password"] == "unapassword"


def test_usare_la_pagina_tiene_fermo_il_watchdog(rete):
    client, finta = rete
    guardia = client.zerocam.netwatch
    finta.hotspot = True
    finta.saved = [{"name": "CasaMia"}]

    client.get("/api/network")

    # Il watchdog stacca l'hotspot per ritentare le reti note: mentre
    # qualcuno e' sulla pagina non deve farlo, o lo butta fuori a meta'
    # configurazione.
    guardia._last_retry = guardia._clock() - netwatch.RETRY_EVERY - 1
    guardia.tick()

    assert finta.hotspot is True


def test_dimenticare_una_rete_senza_nome_non_passa(rete):
    client, finta = rete
    risposta = client.post("/api/network/forget", json={"name": "   "})

    assert risposta.status_code == 400
    assert finta.command("forget") is None
