# -*- coding: utf-8 -*-
"""
Test del watchdog dell'hotspot.

Il tempo e' guidato dal test invece che aspettato: l'orologio del
watchdog e' iniettabile, quindi si puo' far passare mezz'ora fra un giro
e l'altro senza che il test duri mezz'ora. NetworkManager e' sostituito
da una finta che tiene lo stato che terrebbe lui - hotspot su o giu',
connettivita' - cosi' i giri successivi vedono l'effetto dei precedenti.
"""

import pytest

from lib import netwatch


class FakeNM:
    """
    Sta al posto di lib.network, con lo stato che avrebbe NetworkManager.

    Conta le accensioni e gli spegnimenti dell'hotspot, che e' quello su
    cui il watchdog viene giudicato.
    """

    NetworkError = None  # riempita dalla fixture con l'eccezione vera

    def __init__(self):
        self.connectivity_value = "none"
        self.hotspot = False
        self.saved = []
        self.wifi = "wlan0"
        self.started = 0
        self.stopped = 0
        self.fail_start = False
        # Cosa diventa la connettivita' appena la radio si libera: e' il
        # modo per simulare una rete di casa tornata disponibile.
        self.connectivity_when_free = None

    def available(self):
        return True

    def connectivity(self):
        return self.connectivity_value

    def hotspot_active(self):
        return self.hotspot

    def saved_wifi(self):
        return list(self.saved)

    def wifi_device(self):
        return self.wifi

    def hotspot_start(self, ssid, password, ifname="wlan0"):
        if self.fail_start:
            raise self.NetworkError("la radio e' occupata")
        self.started += 1
        self.hotspot = True
        return True

    def hotspot_stop(self):
        self.stopped += 1
        self.hotspot = False
        if self.connectivity_when_free is not None:
            self.connectivity_value = self.connectivity_when_free
        return True


class Orologio:
    """Un tempo che avanza solo quando il test lo dice."""

    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def avanza(self, secondi):
        self.now += secondi


@pytest.fixture
def guardia(monkeypatch, logger):
    from lib import network as vero

    nm = FakeNM()
    nm.NetworkError = vero.NetworkError
    monkeypatch.setattr(netwatch, "network", nm)

    orologio = Orologio()
    watchdog = netwatch.NetworkWatchdog(
        {"hotspot_enabled": True, "hotspot_ssid": "zeroCAM-a1b2",
         "hotspot_password": "unapassword", "hotspot_delay": 120},
        logger, clock=orologio)
    # L'attesa vera dentro la finestra di ritentativo renderebbe il test
    # lungo quanto la finestra.
    monkeypatch.setattr(watchdog._stop, "wait", lambda s=None: orologio.avanza(s or 0))
    return watchdog, nm, orologio


def test_un_buco_breve_non_accende_niente(guardia):
    watchdog, nm, orologio = guardia

    # Un router che si riavvia sparisce per qualche decina di secondi:
    # farci comparire un access point sarebbe solo rumore.
    watchdog.tick()
    orologio.avanza(60)
    watchdog.tick()

    assert nm.started == 0


def test_dopo_lattesa_lhotspot_si_accende(guardia):
    watchdog, nm, orologio = guardia

    watchdog.tick()
    orologio.avanza(130)
    watchdog.tick()

    assert nm.started == 1
    assert nm.hotspot is True


def test_il_cavo_che_torna_spegne_lhotspot(guardia):
    watchdog, nm, orologio = guardia
    nm.hotspot = True
    nm.connectivity_value = "full"

    # Con l'hotspot acceso la connettivita' puo' arrivare solo dal cavo:
    # l'access point ha finito il suo compito.
    watchdog.tick()

    assert nm.hotspot is False
    assert nm.stopped == 1


def test_senza_password_lhotspot_resta_spento(guardia):
    watchdog, nm, orologio = guardia
    watchdog.update_config({"hotspot_enabled": True, "hotspot_password": ""})

    watchdog.tick()
    orologio.avanza(200)
    watchdog.tick()

    # Un access point aperto darebbe a chiunque passi la console di
    # amministrazione: meglio nessun hotspot che quello.
    assert nm.started == 0


def test_disattivato_in_configurazione_viene_tolto(guardia):
    watchdog, nm, orologio = guardia
    nm.hotspot = True
    watchdog.update_config({"hotspot_enabled": False})

    watchdog.tick()

    assert nm.hotspot is False


def test_la_radio_viene_liberata_per_ritentare_le_reti_note(guardia):
    watchdog, nm, orologio = guardia
    nm.hotspot = True
    nm.saved = [{"name": "CasaMia"}]
    watchdog._last_retry = orologio.now
    # La rete di casa e' tornata: si vede solo quando la radio e' libera.
    nm.connectivity_when_free = "full"

    orologio.avanza(netwatch.RETRY_EVERY + 1)
    watchdog.tick()

    assert nm.hotspot is False, "una rete nota ha risposto: l'hotspot resta giu'"
    assert nm.started == 0


def test_se_nessuna_rete_risponde_lhotspot_torna(guardia):
    watchdog, nm, orologio = guardia
    nm.hotspot = True
    nm.saved = [{"name": "CasaMia"}]
    watchdog._last_retry = orologio.now

    orologio.avanza(netwatch.RETRY_EVERY + 1)
    watchdog.tick()

    # Liberata la radio nessuno ha risposto, quindi si torna com'era:
    # altrimenti la webcam resterebbe senza rete e senza hotspot.
    assert nm.stopped == 1
    assert nm.started == 1
    assert nm.hotspot is True


def test_senza_reti_salvate_la_radio_non_si_libera(guardia):
    watchdog, nm, orologio = guardia
    nm.hotspot = True
    nm.saved = []
    watchdog._last_retry = orologio.now

    orologio.avanza(netwatch.RETRY_EVERY + 1)
    watchdog.tick()

    # Non c'e' nessuna rete a cui tornare: staccare l'hotspot servirebbe
    # solo a scollegare chi ci sta configurando sopra.
    assert nm.stopped == 0
    assert nm.hotspot is True


def test_chi_sta_configurando_non_viene_staccato(guardia):
    watchdog, nm, orologio = guardia
    nm.hotspot = True
    nm.saved = [{"name": "CasaMia"}]
    watchdog._last_retry = orologio.now

    orologio.avanza(netwatch.RETRY_EVERY + 1)
    watchdog.note_activity()
    watchdog.tick()

    assert nm.stopped == 0, "la pagina di rete e' in uso proprio ora"

    # Passata la quiete, la finestra si apre come sempre.
    orologio.avanza(netwatch.ACTIVITY_GRACE + 1)
    watchdog.tick()

    assert nm.stopped == 1


def test_anche_il_ritorno_del_cavo_aspetta_che_nessuno_stia_configurando(guardia):
    watchdog, nm, orologio = guardia
    nm.hotspot = True
    nm.connectivity_value = "full"
    watchdog.note_activity()

    watchdog.tick()

    assert nm.hotspot is True, "spegnerlo ora butterebbe fuori chi sta configurando"


def test_un_errore_di_nmcli_non_interrompe_il_giro(guardia):
    watchdog, nm, orologio = guardia
    nm.fail_start = True

    watchdog.tick()
    orologio.avanza(200)
    watchdog.tick()

    # Il tentativo fallisce, ma il watchdog resta in piedi e ci riprovera'.
    assert nm.hotspot is False
    orologio.avanza(200)
    nm.fail_start = False
    watchdog.tick()
    assert nm.hotspot is True


def test_il_nome_della_rete_viene_dallhostname(monkeypatch, logger):
    from lib import network as vero

    nm = FakeNM()
    nm.NetworkError = vero.NetworkError
    monkeypatch.setattr(netwatch, "network", nm)
    monkeypatch.setattr(netwatch.socket, "gethostname", lambda: "zerocam-a1b2")

    watchdog = netwatch.NetworkWatchdog({}, logger)

    # Etichetta, nome della rete e indirizzo da digitare devono dire tutti
    # la stessa cosa, o due webcam accese vicine si confondono.
    assert watchdog.ssid == "zeroCAM-a1b2"

    monkeypatch.setattr(netwatch.socket, "gethostname", lambda: "raspberrypi")
    assert watchdog.ssid == "zeroCAM"

    watchdog.update_config({"hotspot_ssid": "Altro nome"})
    assert watchdog.ssid == "Altro nome"
