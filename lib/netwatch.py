# -*- coding: utf-8 -*-
"""
Hotspot di appoggio quando la webcam resta senza rete.

Il dispositivo viene consegnato già installato: chi lo riceve lo accende e
basta. Se trova una rete che conosce, o un cavo, si collega e non succede
altro. Se non trova nulla, dopo qualche minuto accende un access point
proprio, e da lì l'interfaccia web è raggiungibile per dirgli a quale wifi
collegarsi. Nessun terminale, nessuno schermo.

La radio è una sola: finché l'hotspot è acceso, NetworkManager non può
usarla per cercare le reti conosciute. Per questo ogni tanto l'hotspot
viene spento per un minuto, il tempo di lasciare che ci riprovi da solo,
e riacceso se non è servito. È l'unico modo perché una webcam portata
altrove e poi riportata a casa si ricolleghi senza che nessuno intervenga.

Quella finestra però stacca chi si è collegato all'hotspot proprio per
configurarlo, quindi non si apre mai finché qualcuno sta usando la pagina
di rete: le rotte segnalano la loro attività, e il watchdog aspetta che
sia passato del tempo dall'ultima.
"""

import socket
import threading
import time

from lib import network

# Ogni quanto guardare com'è messa la rete.
POLL_SECONDS = 30
# Quanto tollerare l'assenza di connettività prima di accendere l'hotspot.
# Due minuti coprono un riavvio del router o un DHCP lento senza che l'utente
# veda l'access point comparire per nulla.
DEFAULT_DELAY = 120
# Ogni quanto lasciare libera la radio per ritentare le reti salvate, e per
# quanto tempo. La finestra deve bastare a una scansione più
# un'associazione con DHCP.
RETRY_EVERY = 600
RETRY_WINDOW = 75
# Quiete richiesta dall'ultima attività sulla pagina di rete prima di
# permettersi di toccare l'hotspot.
ACTIVITY_GRACE = 300


class NetworkWatchdog:
    """
    Accende e spegne l'hotspot secondo lo stato della rete.

    Non conserva nulla su disco: lo stato vero è quello di NetworkManager,
    che viene riletto a ogni giro. Quello che tiene in memoria è solo da
    quanto dura una situazione, che è ciò che serve per non reagire a un
    buco di pochi secondi.
    """

    def __init__(self, config, logger, clock=time.monotonic):
        self.logger = logger
        self.cfg = config or {}
        # Iniettabile perché i test guidano il tempo invece di aspettarlo.
        self._clock = clock
        self._stop = threading.Event()
        self._down_since = None
        self._last_retry = None
        self._last_activity = None
        self._warned_about_password = False
        self.poll_seconds = POLL_SECONDS
        self.retry_every = RETRY_EVERY
        self.retry_window = RETRY_WINDOW
        self.activity_grace = ACTIVITY_GRACE

    def update_config(self, config):
        self.cfg = config or {}

    @property
    def enabled(self):
        return bool(self.cfg.get("hotspot_enabled", True))

    @property
    def delay(self):
        try:
            return max(0, int(self.cfg.get("hotspot_delay", DEFAULT_DELAY)))
        except (TypeError, ValueError):
            return DEFAULT_DELAY

    @property
    def password(self):
        return str(self.cfg.get("hotspot_password") or "")

    @property
    def ssid(self):
        """
        Il nome dell'access point.

        Vuoto in configurazione significa ricavarlo dall'hostname, che
        l'installazione rende unico per dispositivo: così l'etichetta
        attaccata alla webcam, il nome della rete e l'indirizzo da digitare
        nel browser dicono tutti la stessa cosa, e due webcam accese vicine
        non si confondono.
        """
        configured = str(self.cfg.get("hotspot_ssid") or "").strip()
        if configured:
            return configured
        try:
            host = socket.gethostname().split(".")[0]
        except Exception:
            host = ""
        if not host or host == "raspberrypi":
            return "zeroCAM"
        # 'zerocam-a1b2' diventa 'zeroCAM-a1b2': stesso nome, maiuscole dove
        # le mette il marchio.
        if host.lower().startswith("zerocam"):
            return "zeroCAM" + host[7:]
        return f"zeroCAM-{host}"

    def note_activity(self):
        """
        Segnala che qualcuno sta usando la pagina di rete.

        Serve a non staccare l'hotspot sotto chi ci è collegato proprio per
        configurare il wifi: la finestra di ritentativo resta chiusa finché
        non è passato del tempo dall'ultima richiesta.
        """
        self._last_activity = self._clock()

    def _quiet(self):
        if self._last_activity is None:
            return True
        return self._clock() - self._last_activity >= self.activity_grace

    def status(self):
        """Come sta l'hotspot, per l'interfaccia web."""
        return {
            "enabled": self.enabled,
            "active": network.hotspot_active(),
            "ssid": self.ssid,
            "password": self.password,
            "delay": self.delay,
        }

    # --- Il ciclo ---

    def start(self):
        thread = threading.Thread(target=self._loop, name="NetworkWatchdog", daemon=True)
        thread.start()
        return thread

    def stop(self):
        self._stop.set()

    def _loop(self):
        self.logger.info("Network watchdog started.")
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception as e:
                # Il watchdog non deve poter portare giù l'applicazione:
                # senza rete la webcam serve a poco, ma con il processo
                # morto non si recupera più nemmeno dall'hotspot.
                self.logger.error(f"Network watchdog tick failed: {e}", exc_info=True)
            self._stop.wait(self.poll_seconds)

    def tick(self):
        """Un giro di controllo. Separato dal ciclo perché i test lo chiamano."""
        if not network.available():
            return

        if not self.enabled:
            # Spento a mano: se l'hotspot è ancora su, va tolto.
            if network.hotspot_active():
                self.logger.info("Hotspot disabled in the configuration: taking it down.")
                self._safely(network.hotspot_stop)
            return

        online = network.connectivity() == "full"
        hotspot = network.hotspot_active()

        if online:
            self._down_since = None
            # Con l'hotspot acceso la connettività può arrivare solo dal
            # cavo: l'access point ha finito il suo compito.
            if hotspot and self._quiet():
                self.logger.info("Connectivity is back: taking the hotspot down.")
                self._safely(network.hotspot_stop)
            return

        if hotspot:
            self._retry_known_networks()
            return

        now = self._clock()
        if self._down_since is None:
            self._down_since = now
            self.logger.warning("No connectivity: the hotspot will come up in "
                                f"{self.delay} seconds if nothing changes.")
            return

        if now - self._down_since >= self.delay:
            self._start_hotspot()

    def _start_hotspot(self):
        if not self.password:
            # Un access point aperto darebbe a chiunque passi la console di
            # amministrazione: meglio nessun hotspot che quello.
            if not self._warned_about_password:
                self.logger.error("No hotspot password configured: the fallback access "
                                  "point stays off. Set one in Network.")
                self._warned_about_password = True
            return

        device = network.wifi_device()
        if not device:
            self.logger.error("No wifi interface: the fallback access point cannot start.")
            return

        self.logger.warning(f"Starting the fallback hotspot '{self.ssid}' on {device}.")
        if self._safely(network.hotspot_start, self.ssid, self.password, device):
            self._down_since = None
            self._last_retry = self._clock()

    def _retry_known_networks(self):
        """
        Spegne l'hotspot per un minuto, per vedere se una rete nota è tornata.

        Con la radio occupata dall'access point NetworkManager non può né
        cercare né riassociarsi, quindi senza questa finestra una webcam
        finita in hotspot ci resterebbe fino al riavvio, anche con il suo
        wifi di casa di nuovo disponibile.
        """
        if not self._safely(network.saved_wifi):
            # Nessuna rete salvata: non c'è niente a cui tornare, e
            # staccare l'hotspot servirebbe solo a scollegare chi lo usa.
            return

        now = self._clock()
        if self._last_retry is not None and now - self._last_retry < self.retry_every:
            return
        if not self._quiet():
            return

        self._last_retry = now
        self.logger.info("Freeing the radio to see whether a known network is back.")
        if not self._safely(network.hotspot_stop):
            return

        deadline = now + self.retry_window
        while self._clock() < deadline and not self._stop.is_set():
            self._stop.wait(5)
            if network.connectivity() == "full":
                self.logger.info("A known network answered: the hotspot stays down.")
                self._down_since = None
                return

        self.logger.info("No known network answered: bringing the hotspot back.")
        self._start_hotspot()

    def _safely(self, action, *args):
        """
        Esegue un comando di rete restituendo il risultato, o None se fallisce.

        Un errore di nmcli qui non è eccezionale — la radio può essere
        occupata, il profilo può non esserci — e non deve interrompere il
        giro: al prossimo si riprova.
        """
        try:
            return action(*args)
        except network.NetworkError as e:
            self.logger.error(f"Network watchdog could not run {action.__name__}: {e}")
            return None
