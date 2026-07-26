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
* Uno scatto notturno può durare minuti: il bracketing prova più combinazioni con due secondi di riscaldamento ciascuna. Se l'intervallo di scatto è breve, i cicli si accodano.
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
* Il caricamento su YouTube richiede l'ambito `youtube.upload`: un refresh token generato prima di questa funzione va rigenerato con `yt_oauth_setup.py`.
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
