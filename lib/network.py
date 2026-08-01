# -*- coding: utf-8 -*-
"""
Lettura e configurazione della rete tramite NetworkManager.

Su Raspberry Pi OS Bookworm la rete la governa NetworkManager, e `nmcli` è
il modo più diretto per parlargli senza tirarsi dentro D-Bus e i suoi
binding. Questo modulo è un guscio sottile attorno al comando: nessuno
stato conservato, nessuna configurazione propria, si limita a chiedere al
sistema com'è messo e a dirgli cosa cambiare.

Due accorgimenti valgono per tutte le chiamate. Il primo è la lingua:
nmcli traduce i suoi output, quindi senza `LC_ALL=C` uno stato
`connected` diventerebbe `connesso` su un dispositivo italiano e nessun
confronto reggerebbe. Il secondo è il timeout: la riconfigurazione di
un'interfaccia può restare appesa parecchio, e la richiesta web che l'ha
chiesta non deve restare appesa con lei.
"""

import ipaddress
import os
import subprocess

# Il nome dei profili che creiamo noi. Serve saperlo per riconoscerli
# fra quelli che l'utente potrebbe aver creato a mano.
HOTSPOT_CONNECTION = "zerocam-hotspot"

# Lettura: risponde subito o è rotto. Attivazione: nmcli aspetta il DHCP,
# l'associazione e l'autenticazione, e su una rete lenta è questione di
# decine di secondi.
READ_TIMEOUT = 15
ACTIVATE_TIMEOUT = 60

# nmcli localizza i suoi output: senza questo, gli stati vanno confrontati
# con la traduzione italiana invece che con la parola che documenta.
_ENV = dict(os.environ, LC_ALL="C", LANG="C")


class NetworkError(Exception):
    """Un comando nmcli è fallito, o nmcli non c'è affatto."""


def _run(args, timeout):
    """
    Esegue nmcli e restituisce lo standard output.

    Isolato in una funzione sua perché è l'unico punto in cui il modulo
    tocca il sistema: i test lo sostituiscono e verificano tutto il resto
    senza una scheda di rete sotto.
    """
    try:
        result = subprocess.run(
            ["nmcli"] + list(args),
            capture_output=True, text=True, env=_ENV, timeout=timeout,
        )
    except FileNotFoundError:
        raise NetworkError("nmcli non è installato su questo sistema.")
    except subprocess.TimeoutExpired:
        raise NetworkError(f"nmcli non ha risposto entro {timeout} secondi.")

    if result.returncode != 0:
        # nmcli mette il motivo su stderr; quando tace, il codice di uscita
        # è tutto quello che possiamo riportare.
        detail = (result.stderr or result.stdout or "").strip()
        raise NetworkError(detail or f"nmcli è uscito con codice {result.returncode}.")

    return result.stdout


def _fields(line):
    """
    Divide una riga in modalità terse nei suoi campi.

    In `-t` nmcli separa con i due punti e protegge con la barra rovescia
    quelli che compaiono dentro un valore: un SSID può contenerli
    entrambi, quindi uno split secco taglierebbe nel posto sbagliato.
    """
    fields, current, escaped = [], [], False
    for char in line:
        if escaped:
            current.append(char)
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == ":":
            fields.append("".join(current))
            current = []
        else:
            current.append(char)
    fields.append("".join(current))
    return fields


def _terse(args, timeout=READ_TIMEOUT):
    """Esegue una lettura in modalità terse e restituisce righe già divise."""
    output = _run(["-t"] + list(args), timeout)
    return [_fields(line) for line in output.splitlines() if line.strip()]


def available():
    """
    Dice se NetworkManager c'è e sta girando.

    L'interfaccia web la chiama prima di mostrare la pagina di rete: su un
    sistema che non lo usa è meglio dire che non si può fare nulla,
    piuttosto che offrire comandi che falliranno tutti.
    """
    try:
        rows = _terse(["-f", "STATE", "general", "status"])
    except NetworkError:
        return False
    return bool(rows) and rows[0][0] not in ("unknown", "asleep")


def connectivity():
    """
    Lo stato di connettività secondo NetworkManager.

    Vale `full`, `limited`, `portal`, `none` o `unknown`. È il giudizio di
    NetworkManager, che interroga per conto suo un endpoint noto: molto più
    affidabile di un ping nostro, perché distingue "ho un IP" da "esco
    davvero verso internet", che è la differenza su cui si decide se
    accendere l'hotspot.
    """
    try:
        rows = _terse(["-f", "CONNECTIVITY", "general", "status"])
    except NetworkError:
        return "unknown"
    return rows[0][0] if rows else "unknown"


# Le sole interfacce che la webcam offre di configurare. È un elenco di
# cose ammesse e non di cose escluse, perché il rischio sta in quello che
# non abbiamo previsto: un tunnel VPN, un bridge, una interfaccia virtuale
# comparirebbero nella pagina con accanto il pulsante per cambiarne
# l'indirizzo, e riconfigurare il tunnel da cui si sta amministrando la
# webcam è il modo più rapido per perderne l'accesso. Il filtro è sul tipo
# e non sul nome: un secondo adattatore wifi su USB resta configurabile,
# anche se non si chiama wlan0.
MANAGEABLE_TYPES = ("ethernet", "wifi")


def devices():
    """
    Le interfacce cablate e wifi viste da NetworkManager.

    Restituisce una lista di dizionari con `device`, `type`, `state` e
    `connection`; quest'ultimo è vuoto se l'interfaccia non ha un profilo
    attivo.
    """
    rows = _terse(["-f", "DEVICE,TYPE,STATE,CONNECTION", "device", "status"])
    result = []
    for row in rows:
        if len(row) < 4:
            continue
        device, kind, state, connection = row[0], row[1], row[2], row[3]
        if kind not in MANAGEABLE_TYPES:
            continue
        result.append({
            "device": device,
            "type": kind,
            "state": state,
            # nmcli scrive '--' dove non c'è un profilo attivo.
            "connection": "" if connection == "--" else connection,
        })
    return result


def address_info(device):
    """
    Indirizzo, gateway, DNS e metodo (automatico o manuale) di un'interfaccia.

    Il metodo non sta fra le proprietà del dispositivo ma in quelle del
    profilo che lo occupa, quindi va chiesto in un secondo momento e solo
    se un profilo c'è.
    """
    info = {"addresses": [], "gateway": "", "dns": [], "method": "", "connection": ""}
    try:
        rows = _terse(["-f", "IP4,GENERAL", "device", "show", device])
    except NetworkError:
        return info

    for row in rows:
        if len(row) < 2:
            continue
        key, value = row[0], row[1]
        if not value or value == "--":
            continue
        # Le chiavi ripetute arrivano indicizzate: IP4.ADDRESS[1], IP4.DNS[2].
        name = key.split("[")[0]
        if name == "IP4.ADDRESS":
            info["addresses"].append(value)
        elif name == "IP4.GATEWAY":
            info["gateway"] = value
        elif name == "IP4.DNS":
            info["dns"].append(value)
        elif name == "GENERAL.CONNECTION":
            info["connection"] = value

    if info["connection"]:
        try:
            rows = _terse(["-f", "ipv4.method", "connection", "show", info["connection"]])
            if rows and len(rows[0]) >= 2:
                info["method"] = rows[0][1]
        except NetworkError:
            pass

    return info


def scan(rescan=True):
    """
    Le reti wifi in portata, la più forte per prima.

    Lo stesso SSID compare una volta per access point: qui resta la
    rilevazione con il segnale migliore, perché all'utente interessa
    scegliere una rete, non un ripetitore. Le reti nascoste non hanno SSID
    e vengono scartate: non si possono scegliere da una lista, si scrivono
    a mano.
    """
    rows = _terse(
        ["-f", "IN-USE,SSID,SIGNAL,SECURITY", "device", "wifi", "list",
         "--rescan", "yes" if rescan else "no"],
        timeout=ACTIVATE_TIMEOUT if rescan else READ_TIMEOUT,
    )

    best = {}
    for row in rows:
        if len(row) < 4:
            continue
        in_use, ssid, signal, security = row[0], row[1], row[2], row[3]
        if not ssid:
            continue
        try:
            signal = int(signal)
        except ValueError:
            signal = 0
        network = {
            "ssid": ssid,
            "signal": signal,
            # Colonna vuota significa rete aperta: nessuna password da chiedere.
            "security": security or "",
            "open": not security,
            "active": in_use.strip() == "*",
        }
        if ssid not in best or signal > best[ssid]["signal"]:
            best[ssid] = network

    return sorted(best.values(), key=lambda n: n["signal"], reverse=True)


def saved_connections():
    """I profili salvati, con tipo e interfaccia su cui sono attivi."""
    rows = _terse(["-f", "NAME,TYPE,DEVICE", "connection", "show"])
    result = []
    for row in rows:
        if len(row) < 3:
            continue
        result.append({
            "name": row[0],
            "type": row[1],
            "device": "" if row[2] == "--" else row[2],
        })
    return result


def saved_wifi():
    """Solo i profili wifi salvati, hotspot escluso."""
    return [c for c in saved_connections()
            if c["type"] == "802-11-wireless" and c["name"] != HOTSPOT_CONNECTION]


def _check_ssid(ssid):
    if not ssid:
        raise NetworkError("Il nome della rete non può essere vuoto.")
    # Il limite è dello standard: 32 byte, non 32 caratteri, e un SSID con
    # accenti ne consuma più di uno per lettera.
    if len(ssid.encode("utf-8")) > 32:
        raise NetworkError("Il nome della rete supera i 32 byte consentiti.")


def _check_psk(password):
    # WPA vuole da 8 a 63 caratteri: sotto, NetworkManager rifiuta il
    # profilo con un errore che all'utente non direbbe nulla.
    if not 8 <= len(password) <= 63:
        raise NetworkError("La password wifi deve avere da 8 a 63 caratteri.")


def wifi_connect(ssid, password="", ifname=None, hidden=False):
    """
    Collega l'interfaccia wifi a una rete, creando o riusando il profilo.

    La password viaggia sulla riga di comando, quindi resta visibile in
    `ps` per il tempo della chiamata: è un compromesso accettato, perché le
    alternative (scrivere il profilo a mano sotto
    /etc/NetworkManager/system-connections) richiedono root, che il
    servizio non ha.

    In caso di fallimento il profilo appena creato viene rimosso: senza,
    una password sbagliata lascerebbe in giro un profilo che
    NetworkManager continuerebbe a ritentare per conto suo.
    """
    _check_ssid(ssid)
    if password:
        _check_psk(password)

    args = ["--wait", str(ACTIVATE_TIMEOUT), "device", "wifi", "connect", ssid]
    if password:
        args += ["password", password]
    if ifname:
        args += ["ifname", ifname]
    if hidden:
        args += ["hidden", "yes"]

    try:
        # Il margine sul timeout di nmcli evita di ucciderlo proprio mentre
        # sta rinunciando: il suo messaggio d'errore è più utile del nostro.
        _run(args, ACTIVATE_TIMEOUT + 10)
    except NetworkError:
        try:
            forget(ssid)
        except NetworkError:
            pass
        raise

    return True


def forget(name):
    """Cancella un profilo salvato."""
    _run(["connection", "delete", name], READ_TIMEOUT)
    return True


def _check_ipv4(address, gateway, dns):
    """
    Controlla indirizzo, gateway e DNS prima di darli a NetworkManager.

    Meglio fermarsi qui che scoprirlo dall'errore di nmcli: a metà
    riconfigurazione l'interfaccia potrebbe già essere giù, e un rifiuto
    che arriva prima di toccare qualsiasi cosa non lascia il dispositivo
    irraggiungibile.
    """
    try:
        interface = ipaddress.ip_interface(address)
    except ValueError:
        raise NetworkError(
            f"'{address}' non è un indirizzo valido: serve la forma 192.168.1.50/24."
        )
    if interface.version != 4:
        raise NetworkError("Sono ammessi solo indirizzi IPv4.")
    # Senza prefisso ip_interface assume /32, che isolerebbe il dispositivo
    # dalla sua stessa rete.
    if "/" not in address:
        raise NetworkError("Manca la lunghezza del prefisso, per esempio /24.")

    if gateway:
        try:
            gw = ipaddress.ip_address(gateway)
        except ValueError:
            raise NetworkError(f"'{gateway}' non è un gateway valido.")
        if gw not in interface.network:
            raise NetworkError(
                f"Il gateway {gateway} non appartiene alla rete {interface.network}."
            )

    for server in dns or []:
        try:
            ipaddress.ip_address(server)
        except ValueError:
            raise NetworkError(f"'{server}' non è un indirizzo DNS valido.")


def set_static(connection, address, gateway="", dns=None):
    """
    Assegna un indirizzo fisso a un profilo e lo riattiva.

    L'ordine non è indifferente: NetworkManager rifiuta un gateway su un
    profilo che non ha ancora un indirizzo, quindi metodo e indirizzo
    vanno nella stessa chiamata, prima di tutto il resto.
    """
    dns = dns or []
    _check_ipv4(address, gateway, dns)

    args = ["connection", "modify", connection,
            "ipv4.method", "manual", "ipv4.addresses", address,
            "ipv4.gateway", gateway,
            # I DNS vanno in una stringa sola separata da spazi.
            "ipv4.dns", " ".join(dns)]
    _run(args, READ_TIMEOUT)
    _run(["--wait", str(ACTIVATE_TIMEOUT), "connection", "up", connection],
         ACTIVATE_TIMEOUT + 10)
    return True


def set_dhcp(connection):
    """
    Riporta un profilo all'indirizzo automatico e lo riattiva.

    Indirizzo, gateway e DNS vanno svuotati esplicitamente: restando lì
    tornerebbero in uso al primo ritorno a `manual`, e i DNS resterebbero
    attivi anche subito, perché NetworkManager li somma a quelli del DHCP.
    """
    _run(["connection", "modify", connection,
          "ipv4.method", "auto",
          "ipv4.addresses", "", "ipv4.gateway", "", "ipv4.dns", ""], READ_TIMEOUT)
    _run(["--wait", str(ACTIVATE_TIMEOUT), "connection", "up", connection],
         ACTIVATE_TIMEOUT + 10)
    return True


def hotspot_active():
    """Dice se l'hotspot creato da noi è quello attivo sull'interfaccia wifi."""
    try:
        return any(d["connection"] == HOTSPOT_CONNECTION for d in devices())
    except NetworkError:
        return False


def hotspot_start(ssid, password, ifname="wlan0"):
    """
    Accende l'hotspot di appoggio.

    La modalità `shared` di NetworkManager porta con sé DHCP e DNS senza
    installare né configurare nulla: il dispositivo si prende 10.42.0.1 e
    distribuisce indirizzi a chi si collega. È il motivo per cui qui non
    compaiono hostapd e dnsmasq.
    """
    _check_ssid(ssid)
    _check_psk(password)
    _run(["--wait", str(ACTIVATE_TIMEOUT), "device", "wifi", "hotspot",
          "ifname", ifname, "con-name", HOTSPOT_CONNECTION,
          "ssid", ssid, "password", password], ACTIVATE_TIMEOUT + 10)

    # nmcli crea il profilo con l'autoconnessione accesa, e lasciarcela
    # rovinerebbe le due cose che contano. All'avvio l'hotspot si
    # prenderebbe la radio prima che le reti salvate possano provarci, e
    # ogni volta che il watchdog lo abbassa per lasciarle ritentare
    # NetworkManager lo rimetterebbe su da solo, rendendo la finestra
    # inutile. L'hotspot deve salire soltanto quando lo decidiamo noi.
    _run(["connection", "modify", HOTSPOT_CONNECTION,
          "connection.autoconnect", "no"], READ_TIMEOUT)
    return True


def hotspot_stop():
    """
    Spegne l'hotspot.

    Il profilo resta salvato, così la riaccensione non ricrea nulla e
    l'SSID non cambia sotto i piedi di chi ha già memorizzato la rete.
    """
    _run(["connection", "down", HOTSPOT_CONNECTION], READ_TIMEOUT)
    return True


def wifi_device():
    """
    Il nome dell'interfaccia wifi, o stringa vuota se non ce n'è una.

    Su Raspberry è `wlan0`, ma con un dongle USB in più l'ordine non è
    garantito: meglio chiederlo che darlo per scontato.
    """
    try:
        for device in devices():
            if device["type"] == "wifi":
                return device["device"]
    except NetworkError:
        pass
    return ""


def status():
    """
    Il quadro completo che serve alla pagina di rete in una chiamata sola.

    Riunisce interfacce, indirizzi, connettività e stato dell'hotspot: la
    pagina si aggiorna a intervalli, e farlo con quattro richieste
    separate significherebbe mostrarle disallineate fra loro.
    """
    if not available():
        return {"available": False, "connectivity": "unknown",
                "devices": [], "hotspot": False}

    result = []
    for device in devices():
        # L'ordine conta: sul nome del profilo comanda `device status`, e
        # un'interfaccia senza indirizzo lo restituisce lo stesso. Al
        # contrario, sovrascrivendo con quello di address_info si
        # perderebbe proprio quando serve, cioè su un profilo che non è
        # ancora salito.
        entry = address_info(device["device"])
        entry.update(device)
        result.append(entry)

    return {
        "available": True,
        "connectivity": connectivity(),
        "devices": result,
        "hotspot": any(d["connection"] == HOTSPOT_CONNECTION for d in result),
    }
