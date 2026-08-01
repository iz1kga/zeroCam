# -*- coding: utf-8 -*-
"""
Test del wrapper su nmcli.

Il comando vero non viene mai eseguito: `network._run` è sostituito da una
finta che registra gli argomenti ricevuti e restituisce l'output deciso
dal test. Quello che si verifica è quindi doppio: che gli output di nmcli
vengano interpretati bene, e che i comandi costruiti siano quelli giusti.
"""

import pytest

from lib import network


class FakeNmcli:
    """
    Sta al posto di nmcli.

    `replies` associa a un frammento della riga di comando l'output da
    restituire; `failures` gli errori da sollevare. Le chiamate restano in
    `calls`, così un test può controllare non solo il risultato ma anche
    cosa è stato chiesto al sistema.
    """

    def __init__(self, replies=None, failures=None):
        self.replies = replies or {}
        self.failures = failures or {}
        self.calls = []

    def __call__(self, args, timeout):
        self.calls.append(list(args))
        line = " ".join(args)
        for needle, message in self.failures.items():
            if needle in line:
                raise network.NetworkError(message)
        for needle, output in self.replies.items():
            if needle in line:
                return output
        return ""

    def command(self, needle):
        """La prima chiamata che contiene il frammento cercato."""
        for call in self.calls:
            if needle in " ".join(call):
                return call
        return None


@pytest.fixture
def nmcli(monkeypatch):
    fake = FakeNmcli()
    monkeypatch.setattr(network, "_run", fake)
    return fake


def test_i_due_punti_dentro_un_ssid_non_dividono_il_campo():
    # nmcli protegge con la barra rovescia i due punti che stanno dentro un
    # valore: uno split secco spezzerebbe l'SSID in due.
    assert network._fields(r"*:casa\:mia:72:WPA2") == ["*", "casa:mia", "72", "WPA2"]
    assert network._fields(r"rete\\strana:60") == [r"rete\strana", "60"]


def test_la_scansione_tiene_il_segnale_migliore_di_ogni_rete(nmcli):
    # Stessa rete vista da due access point, più una nascosta senza SSID.
    nmcli.replies = {"wifi list": "\n".join([
        ":CasaMia:41:WPA2",
        "*:CasaMia:88:WPA2",
        ":ReteAperta:55:",
        "::30:WPA2",
    ]) + "\n"}

    reti = network.scan()

    assert [r["ssid"] for r in reti] == ["CasaMia", "ReteAperta"]
    assert reti[0]["signal"] == 88
    assert reti[0]["active"] is True
    assert reti[1]["open"] is True
    assert reti[0]["open"] is False


def test_solo_le_interfacce_cablate_e_wifi_sono_configurabili(nmcli):
    nmcli.replies = {"device status": "\n".join([
        "lo:loopback:unmanaged:--",
        "eth0:ethernet:connected:Wired connection 1",
        "wlan0:wifi:disconnected:--",
        # Un tunnel VPN: riconfigurarne l'indirizzo dalla pagina
        # significherebbe perdere l'accesso da cui lo si sta facendo.
        "netmaker:wireguard:connected:netmaker",
        "docker0:bridge:unmanaged:--",
    ]) + "\n"}

    interfacce = network.devices()

    assert [d["device"] for d in interfacce] == ["eth0", "wlan0"]
    # nmcli scrive '--' dove non c'è un profilo: la pagina non deve mostrarlo.
    assert interfacce[1]["connection"] == ""
    assert interfacce[0]["connection"] == "Wired connection 1"


def test_un_secondo_adattatore_wifi_resta_configurabile(nmcli):
    # Il filtro è sul tipo e non sul nome: un dongle USB si chiama wlan1 e
    # deve comparire, altrimenti non ci sarebbe modo di configurarlo.
    nmcli.replies = {"device status": "\n".join([
        "wlan0:wifi:connected:CasaMia",
        "wlan1:wifi:disconnected:--",
    ]) + "\n"}

    assert [d["device"] for d in network.devices()] == ["wlan0", "wlan1"]


def test_gli_indirizzi_ripetuti_finiscono_tutti_nella_lista(nmcli):
    nmcli.replies = {
        "device show eth0": "\n".join([
            "IP4.ADDRESS[1]:192.168.1.50/24",
            "IP4.GATEWAY:192.168.1.1",
            "IP4.DNS[1]:8.8.8.8",
            "IP4.DNS[2]:1.1.1.1",
            "GENERAL.CONNECTION:Wired connection 1",
        ]) + "\n",
        "ipv4.method": "ipv4.method:manual\n",
    }

    info = network.address_info("eth0")

    assert info["addresses"] == ["192.168.1.50/24"]
    assert info["dns"] == ["8.8.8.8", "1.1.1.1"]
    assert info["method"] == "manual"
    assert info["connection"] == "Wired connection 1"


def test_una_password_corta_non_arriva_a_nmcli(nmcli):
    # WPA vuole almeno 8 caratteri: fermarsi prima evita un errore di
    # nmcli che all'utente non spiegherebbe nulla.
    with pytest.raises(network.NetworkError):
        network.wifi_connect("CasaMia", "corta")
    assert nmcli.calls == []


def test_una_connessione_fallita_non_lascia_in_giro_il_profilo(nmcli):
    nmcli.failures = {"wifi connect": "Secrets were required, but not provided"}

    with pytest.raises(network.NetworkError):
        network.wifi_connect("CasaMia", "passwordsbagliata")

    # Senza la cancellazione NetworkManager continuerebbe a ritentare da
    # solo con la password sbagliata.
    assert nmcli.command("connection delete") == ["connection", "delete", "CasaMia"]


def test_un_indirizzo_senza_prefisso_viene_rifiutato_prima_di_toccare_la_rete(nmcli):
    # Senza /24 ip_interface assumerebbe /32, isolando il dispositivo dalla
    # sua stessa rete: e a quel punto non sarebbe più raggiungibile per
    # rimediare.
    with pytest.raises(network.NetworkError):
        network.set_static("Wired connection 1", "192.168.1.50")
    assert nmcli.calls == []


def test_un_gateway_fuori_dalla_rete_viene_rifiutato(nmcli):
    with pytest.raises(network.NetworkError):
        network.set_static("Wired connection 1", "192.168.1.50/24", gateway="10.0.0.1")
    assert nmcli.calls == []


def test_un_dns_non_valido_viene_rifiutato(nmcli):
    with pytest.raises(network.NetworkError):
        network.set_static("Wired connection 1", "192.168.1.50/24",
                           gateway="192.168.1.1", dns=["8.8.8.8", "non-un-ip"])
    assert nmcli.calls == []


def test_lindirizzo_fisso_viene_scritto_e_il_profilo_riattivato(nmcli):
    network.set_static("Wired connection 1", "192.168.1.50/24",
                       gateway="192.168.1.1", dns=["8.8.8.8", "1.1.1.1"])

    modifica = nmcli.command("connection modify")
    assert "manual" in modifica
    assert modifica[modifica.index("ipv4.addresses") + 1] == "192.168.1.50/24"
    assert modifica[modifica.index("ipv4.gateway") + 1] == "192.168.1.1"
    # I DNS vanno in una stringa sola separata da spazi.
    assert modifica[modifica.index("ipv4.dns") + 1] == "8.8.8.8 1.1.1.1"
    # Modificare il profilo non basta: senza riattivarlo resta in uso il vecchio.
    assert nmcli.command("connection up") is not None


def test_il_ritorno_al_dhcp_svuota_i_campi_manuali(nmcli):
    network.set_dhcp("Wired connection 1")

    modifica = nmcli.command("connection modify")
    assert "auto" in modifica
    # Restando lì, i DNS manuali si sommerebbero a quelli del DHCP e
    # l'indirizzo tornerebbe al primo ritorno a 'manual'.
    for campo in ("ipv4.addresses", "ipv4.gateway", "ipv4.dns"):
        assert modifica[modifica.index(campo) + 1] == ""


def test_lhotspot_rifiuta_una_password_troppo_corta(nmcli):
    with pytest.raises(network.NetworkError):
        network.hotspot_start("zeroCAM-1234", "corta")
    assert nmcli.calls == []


def test_lhotspot_nasce_in_modalita_condivisa_col_nome_previsto(nmcli):
    network.hotspot_start("zeroCAM-1234", "unapassword", ifname="wlan0")

    comando = nmcli.command("wifi hotspot")
    assert comando[comando.index("con-name") + 1] == network.HOTSPOT_CONNECTION
    assert comando[comando.index("ssid") + 1] == "zeroCAM-1234"
    assert comando[comando.index("ifname") + 1] == "wlan0"


def test_lhotspot_non_deve_riaccendersi_da_solo(nmcli):
    network.hotspot_start("zeroCAM-1234", "unapassword")

    # Con l'autoconnessione accesa l'hotspot si riprenderebbe la radio
    # all'avvio, prima che le reti salvate possano provarci, e ogni volta
    # che il watchdog la libera per lasciarle ritentare.
    modifica = nmcli.command("connection.autoconnect")
    assert modifica[modifica.index("connection.autoconnect") + 1] == "no"
    assert network.HOTSPOT_CONNECTION in modifica


def test_lhotspot_attivo_si_riconosce_dal_nome_del_profilo(nmcli):
    nmcli.replies = {"device status":
                     f"wlan0:wifi:connected:{network.HOTSPOT_CONNECTION}\n"}
    assert network.hotspot_active() is True

    nmcli.replies = {"device status": "wlan0:wifi:connected:CasaMia\n"}
    assert network.hotspot_active() is False


def test_senza_nmcli_lo_stato_e_una_risposta_e_non_un_errore(monkeypatch):
    # Fuori dal Raspberry nmcli può non esserci: la pagina deve poter dire
    # che non si configura nulla, invece di rompersi.
    def assente(args, timeout):
        raise network.NetworkError("nmcli non è installato su questo sistema.")

    monkeypatch.setattr(network, "_run", assente)

    stato = network.status()
    assert stato["available"] is False
    assert stato["devices"] == []
    assert network.connectivity() == "unknown"
    assert network.wifi_device() == ""


def test_lo_stato_unisce_interfacce_indirizzi_e_connettivita(nmcli):
    nmcli.replies = {
        "general status": "full\n",
        "device status": "eth0:ethernet:connected:Wired connection 1\n",
        "device show eth0": "\n".join([
            "IP4.ADDRESS[1]:192.168.1.50/24",
            "GENERAL.CONNECTION:Wired connection 1",
        ]) + "\n",
        "ipv4.method": "ipv4.method:auto\n",
    }

    stato = network.status()

    assert stato["available"] is True
    assert stato["connectivity"] == "full"
    assert stato["hotspot"] is False
    assert stato["devices"][0]["addresses"] == ["192.168.1.50/24"]
    assert stato["devices"][0]["method"] == "auto"
    assert stato["devices"][0]["connection"] == "Wired connection 1"


def test_il_nome_del_profilo_sopravvive_a_uninterfaccia_senza_indirizzo(nmcli):
    # Un profilo che non è ancora salito non compare in `device show`: il
    # nome deve arrivare da `device status`, o la pagina non saprebbe su
    # quale profilo scrivere l'indirizzo fisso.
    nmcli.replies = {
        "general status": "none\n",
        "device status": "wlan0:wifi:connecting:CasaMia\n",
        "device show wlan0": "IP4.ADDRESS:--\n",
    }

    stato = network.status()

    assert stato["devices"][0]["connection"] == "CasaMia"
    assert stato["devices"][0]["addresses"] == []
