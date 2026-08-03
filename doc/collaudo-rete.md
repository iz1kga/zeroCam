# Collaudo della rete sul dispositivo

Promemoria delle prove da fare su un Raspberry vero. Serve perché la
gestione della rete è provata solo con `nmcli` sostituito da una finta: i
test verificano che i comandi costruiti siano quelli giusti, non che
NetworkManager risponda come ci si aspetta.

Questo file non entra nel manuale: `build.sh` raccoglie solo i capitoli
numerati.

Tenere aperto un terminale con il log per tutta la sessione:

```bash
journalctl -u zerocam -f
```

## 1. Dopo l'installazione

```bash
hostname                       # atteso: zerocam-XXXX
hostnamectl status | head -3
grep 127.0.1.1 /etc/hosts      # deve riportare lo stesso nome
nmcli -t -f STATE,CONNECTIVITY general status
rfkill list                    # 'Soft blocked: no' su Wireless LAN
iw reg get | head -3           # il paese impostato, non '00'
systemctl is-active avahi-daemon
```

Da un altro computer sulla stessa rete:

```bash
ping zerocam-XXXX.local
avahi-browse -at | grep -i zerocam    # serve avahi-utils
```

L'annuncio del servizio deve portare il nome di *Device Details*, non
l'hostname. Cambiandolo dall'interfaccia e salvando, il file va riscritto:

```bash
cat /etc/avahi/services/zerocam.service
ls -l /etc/avahi/services/zerocam.service    # proprietario: utente del servizio
```

## 2. Permessi (polkit)

È il punto in cui è più probabile trovare una sorpresa: la regola concede
a un utente senza sessione le azioni di NetworkManager, che di norma
vogliono un'autenticazione interattiva.

```bash
sudo ls -l /etc/polkit-1/rules.d/10-zerocam-network.rules
sudo ls -1 /usr/share/polkit-1/rules.d/
```

Il nome deve cominciare per `10-`: polkit valuta i file in ordine alfabetico
e si ferma al primo che risponde, e `49-polkit-pkla-compat.rules` risponde
prima. Con la numerazione `50-` la regola risulta caricata, il log di polkit
non segnala nulla, e ogni modifica fallisce lo stesso.

La prova vera si fa dall'interfaccia: **Network → Address** su `eth0`,
mettere un indirizzo fisso, poi rimetterlo in DHCP. Se il log riporta
`Insufficient privileges`, la regola non ha effetto; l'audit di
NetworkManager conferma di chi era il tentativo:

```bash
sudo journalctl -u NetworkManager | grep 'result="fail"'
```

Attenzione a due prove che sembrano equivalenti e non lo sono. Provare con
`sudo -u <utente> nmcli` da un terminale non riproduce il caso vero: quel
processo eredita una sessione di login, e polkit tratta diversamente un
soggetto con sessione da un servizio che non ne ha. E `polkit.log()` dentro
una regola può non comparire nel journal, quindi la sua assenza non prova
che la regola non sia stata eseguita. L'unica prova affidabile è
un'operazione di scrittura fatta dalla pagina.

Cambiando l'indirizzo dell'interfaccia da cui si sta navigando la pagina
resta senza risposta e dopo venticinque secondi lo dice: è il
comportamento previsto, non un errore. Conviene fare questa prova dal
wifi, per non perdere la sessione.

## 3. Wifi

- **Scan networks**: l'elenco deve comparire in pochi secondi, ordinato per
  segnale, senza duplicati dello stesso SSID.
- **Connessione** a una rete vera, con il cavo ancora attaccato: entrambe
  le interfacce restano su, e il traffico continua a uscire dal cavo.
  `ip route` deve mostrare la rotta di `eth0` con metrica più bassa.
- **Password sbagliata**: deve tornare l'errore vero di `nmcli`, e in
  `nmcli connection show` non deve restare nessun profilo con quel nome.
- **Forget**: il profilo sparisce da `nmcli connection show`.

## 4. Hotspot

La prova che conta di più, ed è quella che riproduce la giornata
dell'utente finale.

```bash
# Staccare il cavo e non toccare nulla.
# Atteso nel log, in quest'ordine:
#   No connectivity: the hotspot will come up in 120 seconds if nothing changes.
#   Starting the fallback hotspot 'zeroCAM-XXXX' on wlan0.
```

A hotspot acceso, la verifica che nessun test poteva fare:

```bash
nmcli -t -f connection.autoconnect connection show zerocam-hotspot
# deve dire 'no'
```

Se dicesse `yes`, NetworkManager si riprenderebbe la radio da solo e la
finestra di ritentativo non funzionerebbe mai.

Poi, dal telefono:

1. Inquadrare il primo QR dell'etichetta: il telefono si collega alla rete.
2. Inquadrare il secondo: si apre `http://10.42.0.1:8080/`.
3. Entrare con `admin` e la password dell'interfaccia.
4. Dalla pagina *Network*, collegare il wifi di casa.

La pagina smette di rispondere appena l'hotspot si spegne: è previsto.

### Password sbagliata dall'hotspot

Il caso che decide se un utente inesperto resta chiuso fuori. Dal telefono
collegato all'hotspot, inserire una password wifi errata. La rete
dell'hotspot deve ricomparire entro un paio di minuti. Nel log:

```
Wifi connection to 'CasaMia' failed: ...
Wifi attempt failed: the hotspot is back up.
```

Se la prima protezione non scattasse, deve intervenire il watchdog:

```
No connectivity: the hotspot will come up in 120 seconds if nothing changes.
```

### Finestra di ritentativo

Con l'hotspot acceso, una rete salvata e quella rete di nuovo
raggiungibile, **non toccare la pagina per dieci minuti**. Atteso:

```
Freeing the radio to see whether a known network is back.
A known network answered: the hotspot stays down.
```

Toccando la pagina *Network* entro cinque minuti, la finestra non si deve
aprire: è la protezione che evita di scollegare chi sta configurando.

## 5. Installazione da zero

Il percorso meno collaudato: finora l'installatore ha girato quasi sempre
in aggiornamento, dove i rami della prima installazione (`.env`, prima
password, `.conf.json` iniziale, hostname, hotspot) non vengono percorsi.

Su un Raspberry vergine:

1. Installare e verificare il riquadro finale con i quattro valori.
2. Controllare che l'etichetta PNG sia stata scritta in
   `/usr/local/zerocam/data/etichetta-<hostname>.png`.
3. **Rilanciare l'installatore sullo stesso dispositivo**: deve dire che
   hostname, hotspot e password erano già a posto e non cambiare nulla.
   La password dell'hotspot, ormai cifrata, non deve comparire come
   `enc:...` ma come "invariata".
4. Provare `sudo bash zerocamInstall` da una shell di root: deve
   rifiutarsi di partire.

## Cosa resta fuori

Non implementato di proposito, da non cercare durante il collaudo:

- **Captive portal**: collegandosi all'hotspot il telefono non apre la
  pagina da solo, l'indirizzo va inquadrato o digitato.
- **Forzare l'hotspot dall'interfaccia**: non c'è un pulsante "accendi
  ora", si aspettano i due minuti.
- **IPv6**: l'indirizzo fisso è solo IPv4.
- **WPA-Enterprise**: reti aziendali con utente e certificato non sono
  gestite.
- **Rinomina dell'hostname dall'interfaccia**: si decide
  all'installazione.
