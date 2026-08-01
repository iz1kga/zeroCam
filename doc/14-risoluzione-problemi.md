# Risoluzione dei problemi

## Prima di tutto

Tre comandi risolvono, o almeno spiegano, la maggior parte dei casi:

```bash
sudo systemctl status zerocam.service
tail -n 200 /usr/local/zerocam/data/logs/zerocam.log
journalctl -u zerocam.service -n 100
```

## L'interfaccia web non risponde

Verificare che il servizio sia attivo. Se non parte, il log di systemd dice quasi sempre perché:

* `ZEROCAM_SECRET_KEY environment variable not set` — manca o è illeggibile `data/.env`, o il servizio punta al percorso sbagliato.
* `DEVICE_ID environment variable not set` — stessa origine.
* `Configuration file not found` — manca `data/.conf.json`.

L'assenza di rete non è più fra le cause: l'applicazione la guarda all'avvio ma non la aspetta, e scrive `No internet connection: starting anyway`. È voluto. Una webcam appena accesa dove verrà usata non ha ancora una rete, ed è esattamente il momento in cui servono l'interfaccia web per dargliene una e l'hotspot per raggiungerla: fermandosi lì non mostrerebbe nulla e l'unico modo per configurarla sarebbe un terminale.

## La pagina Network dice che NetworkManager non risponde

Il sistema è più vecchio di Bookworm, e configura la rete con `dhcpcd` e `wpa_supplicant`. `nmcli general status` lo conferma: se il comando non esiste, non c'è nulla da configurare da lì. La rete va impostata a mano dal terminale, e per il resto zeroCAM su quelle versioni non è supportato.

## Il wifi non si collega

* Una password sbagliata dà `Secrets were required, but not provided`. Il profilo appena creato viene cancellato da solo, quindi basta riprovare: se ne resta uno vecchio con la password sbagliata, si cancella con **Dimentica**.
* La radio può essere bloccata quando il paese non è impostato: `rfkill list` mostra `Soft blocked: yes`. Si rimedia con `sudo raspi-config nonint do_wifi_country IT`.
* Una rete che non compare nella scansione può essere nascosta, e allora va scritta a mano, oppure a 5 GHz su un canale che il paese impostato non consente.

## La pagina Network legge ma non salva

Manca il permesso: il servizio gira come utente normale, e senza la regola polkit NetworkManager rifiuta ogni modifica. Nel log dell'applicazione il messaggio è `Insufficient privileges`, e in quello di NetworkManager compare la riga corrispondente:

```bash
sudo ls -l /etc/polkit-1/rules.d/10-zerocam-network.rules
sudo journalctl -u NetworkManager | grep 'result="fail"'
```

Se il file non c'è, lo crea un aggiornamento; in alternativa si rilancia l'installatore, che è idempotente.

**Se il file c'è e il rifiuto resta, guardare il nome.** Una regola numerata `50-` viene caricata ma mai eseguita, perché `49-polkit-pkla-compat.rules` risponde prima e interrompe la valutazione. È un guasto silenzioso: polkit dichiara di aver caricato il file e non registra nessun errore. Il nome giusto comincia per `10-`, e un residuo `50-zerocam-network.rules` di un'installazione precedente si può cancellare.

## `zerocam-XXXX.local` non risponde

* Avahi può non essere attivo: `systemctl status avahi-daemon`.
* Il client deve saper risolvere gli indirizzi `.local`: Windows lo fa dalla 10 in poi, Android solo da alcune versioni. Da un telefono che non ce la fa, resta l'indirizzo IP, che la pagina *Network* mostra.
* Due dispositivi con lo stesso nome fanno rinominare il secondo in `zerocam-2.local`. Non dovrebbe succedere, perché il nome porta il suffisso del seriale, ma succede se l'hostname è stato imposto a mano uguale su entrambi.

## L'hotspot non compare

* Senza password configurata l'hotspot non parte: aperto darebbe a chiunque passi l'accesso alla console. Il log lo dice una volta sola, `No hotspot password configured`. Si imposta in **Configuration → Network**.
* L'attesa predefinita è di due minuti dall'ultima connettività: prima di allora non compare nulla, ed è voluto, altrimenti un router che si riavvia lo farebbe apparire per niente.
* La radio può essere bloccata se il paese non è impostato: `rfkill list` mostra `Soft blocked: yes`, e si rimedia con `sudo raspi-config nonint do_wifi_country IT`.
* Il log racconta ogni decisione: `No connectivity: the hotspot will come up in 120 seconds`, poi `Starting the fallback hotspot`.

## L'hotspot si spegne da solo mentre lo sto usando

Non mentre lo si usa: ogni dieci minuti il watchdog lo abbassa per poco più di un minuto, per lasciare che NetworkManager riprovi con le reti che conosce — senza, una webcam finita in hotspot ci resterebbe anche con il suo wifi di nuovo disponibile. La finestra però non si apre finché la pagina *Network* è in uso, e comunque non si apre affatto se non ci sono reti salvate a cui tornare. Se capita, sono passati più di cinque minuti dall'ultima richiesta: basta ricaricare la pagina e l'hotspot torna entro un paio di minuti.

## Ho sbagliato la password del wifi e la webcam è sparita

È il caso previsto. Collegandosi a una rete l'hotspot si spegne, perché la radio è una sola; se la password è sbagliata la connessione fallisce e l'hotspot viene rimesso su subito. Se anche quello non riesce, ci pensa il watchdog al giro successivo. In pratica, entro un paio di minuti la rete dell'hotspot ricompare e si può riprovare.

## L'indirizzo fisso non è stato applicato, o così sembra

Se lo si è cambiato sull'interfaccia da cui si stava navigando, la risposta non poteva tornare: la connessione è caduta con il vecchio indirizzo. La modifica di solito è andata a buon fine. Lo dice il log:

```
Profile 'Wired connection 1' switched to the fixed address 192.168.1.50/24
```

Se invece il log riporta un errore di `nmcli`, la vecchia configurazione è ancora in uso e il dispositivo resta raggiungibile dov'era.

## Non vengono scattate foto

* Controllare che la fase del giorno sia riconosciuta: `Day period is 'unknown', skipping capture` indica coordinate o offset incoerenti in Device Details.
* Uno scatto notturno può durare minuti: il bracketing prova più combinazioni con due secondi di riscaldamento ciascuna. Se l'intervallo di scatto è breve, i cicli si accodano. Per distinguere una cattura lunga da un blocco basta il log: le righe `[Ns] Tentativo k/40` avanzano finché il software lavora, e il pulsante di Cam Control mostra da quanto tempo è in corso lo scatto. Se invece il tempo si ferma su un tentativo per molti minuti, il problema è nel sensore.
* `Failed to capture image (buffer is None)` indica un problema del sensore: se si ripete, un *hard reset* automatico (o un riavvio) di solito lo risolve.
* Con la pagina Focus Aid aperta il ciclo di scatto è in pausa per costruzione.

## Le immagini sono troppo scure o troppo chiare

Agire su *Min/Max Target Brightness* nella fase interessata: sono la luminosità media che il bracketing insegue. Alzarli produce immagini più chiare, con pose più lunghe e più rumore.

Se il problema si presenta solo nelle ore di passaggio, il colpevole sono di solito gli offset di Device Details: la webcam sta usando i parametri della fase sbagliata. Su un versante in ombra conviene alzare le soglie del giorno.

## La diretta non va in onda

* **Nessun dato arriva a YouTube**: controllare *Streaming Enabled* e la chiave di streaming. Nel log, `No YouTube liveStream matches the configured stream key` significa che la chiave non corrisponde ad alcuno stream dell'account.
* **I dati arrivano ma la diretta non parte**: è il caso che *Auto broadcast* risolve. Senza broadcast collegato YouTube riceve il flusso senza mandarlo in onda.
* **La diretta va in "testing"**: succede quando il monitor stream è attivo sul broadcast; quelli creati da zeroCAM lo disattivano, ma un broadcast creato a mano nella Live Control Room può averlo.
* **Lo streaming si interrompe di continuo**: cercare `Broken pipe with ffmpeg`. Se compare a ogni ciclo, il comando di ffmpeg fallisce all'avvio — chiave errata, destinazione aggiuntiva malformata, o filtro mancante (vedi sotto).
* **Frame skipped for YouTube (ffmpeg busy)**: la codifica non sta al passo. Ridurre risoluzione, framerate o bitrate.
* **L'autenticazione non parte**: se premendo *Autentica* compare "Credenziali non valide o client OAuth del tipo sbagliato", il client creato sulla Cloud Console non è di tipo *TV e dispositivi di immissione limitata*. Il device flow non accetta client desktop o web.
* **Il codice non viene mai accettato**: il codice scade dopo mezz'ora. Se nel log compare `YouTube device flow ended: expired_token` basta premere di nuovo *Autentica* e rifare l'inserimento. `access_denied` significa invece che l'autorizzazione è stata rifiutata, o concessa a un account che non amministra il canale.
* **`The user is not enabled for live streaming` (403)**: il token è stato rilasciato su un canale diverso da quello della stream key, oppure su un canale che non ha le dirette abilitate. Al termine dell'autenticazione l'interfaccia dice su quale canale si è autenticata: se non è quello giusto, ripetere *Autentica* scegliendo l'account corretto (per un canale Brand va selezionato durante l'autorizzazione). Se il canale è quello giusto, abilitare le dirette su [youtube.com/features](https://www.youtube.com/features): richiede la verifica del numero di telefono e la prima attivazione può richiedere 24 ore.
* **Tutto funziona per una settimana, poi la diretta non parte più**: la schermata di consenso OAuth è rimasta in stato *Testing*, dove Google revoca i refresh token dopo sette giorni. Portare l'app **In produzione** e rigenerare il token.
* **La diretta ha ancora la data di ieri nel titolo**: il ricambio giornaliero è disattivato o l'orario non è valido. A ogni ripartenza il log lo dichiara: `Reusing YouTube broadcast <id> (daily reset not configured)` oppure `(daily reset '25:70' is not a valid HH:MM, rollover disabled)`. Con il campo compilato correttamente compare invece `(started after the daily reset of 27/07/2026 00:00)` finché la diretta è più recente dell'orario, e al primo scatto successivo `Broadcast <id> started at ..., before the daily reset of ...: creating a new one`.

## ONVIF non funziona del tutto

* **Le informazioni del dispositivo arrivano, i profili media no** (`No route to host` verso un indirizzo `192.168.x.x`): il client sta seguendo un indirizzo che zeroCAM gli ha dichiarato e che dal suo punto di rete non esiste. Dalle versioni recenti gli indirizzi dichiarati seguono quello con cui il client ha contattato la webcam; se l'errore persiste, il client sta usando un URL memorizzato in precedenza e va ricreato.
* **Nessun URI dell'istantanea**: `/snapshot.jpg` esiste solo con lo streaming attivo, perché è il fotogramma condiviso che lo streaming produce.
* **Il client chiede le credenziali in continuazione**: l'utente è `onvif` e la password quella della pagina ONVIF; con *allow_unsecure* l'istantanea è invece libera.

## L'interfaccia in HTTPS

* **`ERR_CONNECTION_RESET` o «connessione reimpostata»**: succedeva aprendo `http://` sulla porta dell'HTTPS. Ora quella richiesta riceve un redirect verso `https://`; se l'errore si ripresenta, la porta indicata non è quella dell'HTTPS o davanti c'è un firewall.
* **«Il certificato non è attendibile»**: è previsto, il certificato è autofirmato. Va accettato una volta. Per accertarsi che sia davvero quello della webcam, confrontare l'impronta SHA-256 mostrata dal browser con quella scritta nel log all'avvio.
* **Un programma che scaricava l'istantanea ha smesso**: il redirect risolve il caso del browser, non quello dei client che non lo seguono — i consumatori ONVIF e gli script che scaricano `/snapshot.jpg` di solito non lo fanno, e non accettano un certificato autofirmato. Il log li mostra come `Plain HTTP request from <indirizzo> ... redirected to ...` che si ripete. Vanno indirizzati alla porta HTTP, che per loro va lasciata aperta.
* **«Il certificato non è valido per questo nome»**: si sta raggiungendo la webcam con un nome che il certificato non contiene. Va aggiunto in **System → Nomi da includere nel certificato**, poi riavviata l'applicazione: il certificato viene rigenerato.

## L'annotazione non compare sul video

* Verificare che *Annotazione e loghi nella diretta* sia attiva e che sia passato uno scatto: il filtro si costruisce all'avvio dello streaming.
* Verificare che ffmpeg abbia il filtro necessario:

  ```bash
  ffmpeg -filters | grep drawtext
  ```

  Se manca, il build installato è privo di libfreetype e ffmpeg esce subito all'avvio dello streaming.
* Nel log devono comparire le righe `Stream overlay ...` con posizione e scala dei loghi.

## I loghi hanno la dimensione sbagliata

La scala riduce soltanto: un valore superiore a 100 non ingrandisce, né sulla foto né sul video. Per un logo più grande serve un file sorgente più grande. Le coordinate si riferiscono all'immagine dopo il ritaglio.

## Le maschere privacy non coprono la zona giusta sul video

Le maschere vengono riproiettate dall'inquadratura della foto a quella dello streaming leggendo dalla camera la porzione di sensore usata. Se il dato non è disponibile il software ripiega su un ritaglio centrato e lo scrive nel log (`Falling back to a centred ... crop for the stream view`). In quel caso conviene allargare un poco i poligoni.

Ricordare che sul video le maschere entrano in vigore al riavvio dello streaming, non subito.

## Il timelapse non viene montato

* `Timelapse is disabled, no job scheduled` — la funzione è spenta.
* Sotto la soglia *Minimo per montare* il montaggio non parte: succede la prima settimana, o dopo un periodo di fermo.
* Il caricamento su YouTube ha bisogno di un token con i permessi giusti: un refresh token generato prima che il timelapse esistesse va rifatto una volta con il pulsante *Autentica* in **Configuration → Stream**.
* Giorno e ora del montaggio si applicano al riavvio dell'applicazione.

## Lo spazio su disco si riempie

Nell'ordine: fotogrammi del timelapse (regolati dalla finestra di conservazione), archivio immagini di debug (nessuna pulizia automatica), video montati conservati sul dispositivo.

```bash
du -sh /usr/local/zerocam/data/*
```

## Le password nella configurazione risultano illeggibili

Nel log compare `Errore durante la decrittografia ... Controllare che ZEROCAM_SECRET_KEY sia corretta`. Significa che la chiave attuale non è quella con cui i valori furono cifrati: tipicamente `data/.env` è stato ricreato. Le password vanno reinserite dall'interfaccia, oppure si ripristina un backup dalla pagina System.

## Dopo un aggiornamento manca qualcosa

Al primo avvio l'applicazione sposta nella cartella dei dati quanto trova ancora in quella dell'applicazione e lo scrive nel log (`Moved ... to the data directory`). Se un file risulta presente in entrambe, la copia vecchia viene lasciata dov'è e il log lo segnala: in quel caso si sceglie a mano quale tenere.
