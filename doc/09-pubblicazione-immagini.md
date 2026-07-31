# Pubblicazione delle immagini

Ogni scatto, una volta elaborato, può prendere fino a tre strade: un server FTP, un endpoint HTTP e la copia locale servita dall'interfaccia. Sono indipendenti fra loro e nessuna è obbligatoria.

## Upload FTP

**Configuration → FTP Upload** è la via classica per alimentare un sito web.

| Campo | Significato |
|---|---|
| Upload FTP attivo | Abilita il caricamento; spento, il resto della configurazione resta dov'è |
| Host, Port | Server FTP e porta (di norma 21) |
| Username, Password | Credenziali; la password è cifrata in configurazione |
| Folder | Cartella remota in cui entrare prima del caricamento |
| Filename | Nome del file remoto, sempre lo stesso a ogni scatto |
| Timeout | Secondi di attesa massima per la connessione |

Il trasferimento avviene in modalità passiva e sovrascrive ogni volta lo stesso file: il sito mostra così l'immagine più recente senza dover gestire uno storico. Un errore di rete viene registrato nel log e non interrompe il ciclo: lo scatto successivo riproverà.

L'interruttore in cima alla pagina lo spegne senza cancellare nulla: le installazioni che avevano l'FTP configurato prima che l'interruttore esistesse se lo trovano acceso, quindi il comportamento non cambia da solo con l'aggiornamento.

## Upload HTTP

**Configuration → HTTP Upload** invia l'immagine a un servizio che la riceve via API.

| Campo | Significato |
|---|---|
| Enabled | Attiva l'invio |
| Endpoint URL | Indirizzo a cui inviare la richiesta |
| Bearer Token | Token di autorizzazione, cifrato in configurazione |
| Timeout (s) | Attesa massima della risposta |
| Send Timestamp | Aggiunge alla richiesta l'istante dello scatto in UTC |

La richiesta è un `POST multipart/form-data` con il campo `image` (JPEG) e, se richiesto, il campo `timestamp` in formato `AAAA-MM-GGTHH:MM:SSZ`. L'autorizzazione viaggia nell'intestazione `Authorization: Bearer <token>`.

Le risposte vengono interpretate e registrate nel log in modo comprensibile:

| Codice | Interpretazione |
|---|---|
| 201 | Caricamento riuscito |
| 409 o codice `DUPLICATE_DATA` | Immagine già presente: avviso, non errore |
| 401 | Token non valido |
| 403 | Webcam disabilitata lato server |
| 400 | Richiesta malformata |

## Ultima immagine locale

L'ultimo scatto viene sempre salvato come `data/latest.jpg` e servito dall'interfaccia all'indirizzo `/latest.jpg`. È la stessa immagine mostrata in Cam Control.

Poiché la rotta richiede la sessione autenticata, non è utilizzabile come sorgente diretta per un sito pubblico: per quello si usano FTP o HTTP.

## Ordine delle operazioni

L'immagine caricata è quella definitiva, elaborata in questo ordine:

```
scatto → maschera di contrasto → ritaglio → maschere privacy
      → barra di annotazione → loghi → metadati → upload e salvataggi
```

Lo stesso file alimenta anche il fotogramma del timelapse: ciò che si vede nel video settimanale è esattamente quanto è stato pubblicato.

I metadati vengono reinseriti in fondo, subito prima delle destinazioni: l'elaborazione con PIL li perderebbe, e reinserirli una volta sola fa sì che l'immagine su FTP, quella caricata via HTTP, `latest.jpg`, l'archivio di diagnosi e il fotogramma del timelapse portino tutti gli stessi dati di scatto. Cosa contengono è descritto nel capitolo sul timelapse; il campo che serve più spesso è `ColourGains`, con i guadagni di bianco scelti dall'automatismo. Il peso aggiunto è di circa mezzo kilobyte per immagine.

Vale la pena saperlo se le immagini finiscono su un sito pubblico: insieme allo scatto viaggiano esposizione, guadagni, temperatura del colore e temperatura del sensore. Non c'è alcun dato di posizione.
