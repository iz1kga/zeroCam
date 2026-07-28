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

All'avvio l'applicazione attende la connessione a Internet, riprovando ogni 60 secondi: se la rete non c'è, il servizio risulta attivo ma l'interfaccia non risponde ancora. Il log lo scrive: `No internet connection. Retrying in 60 seconds...`.

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
