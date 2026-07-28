# Streaming in diretta

## Come funziona

Il Raspberry Pi produce fotogrammi grezzi che ffmpeg codifica in H.264 e spinge via RTMP verso YouTube — e, se richiesto, verso altre destinazioni. All'audio provvede una traccia silenziosa generata da ffmpeg, necessaria perché YouTube accetti il flusso.

![Percorso dei fotogrammi durante lo streaming: il flusso principale va a ffmpeg, quello ridotto alimenta ONVIF e l'anteprima.](img/pipeline-streaming.png){ width=100% }

Lo streaming si ferma a ogni scatto e riparte subito dopo: la camera non può servire contemporaneamente la cattura a piena risoluzione e il video. Sono pochi secondi, e la diretta è configurata per sopravvivere all'interruzione senza chiudersi.

## Parametri dello streaming

**Configuration → Stream**

| Campo | Significato |
|---|---|
| Streaming Enabled | Attiva la trasmissione |
| YouTube Stream Key | Chiave di streaming presa da YouTube Studio; cifrata in configurazione |
| Resolution | Larghezza e altezza del video, per esempio 2560×1440 |
| Destinazioni aggiuntive | Altri URL RTMP verso cui ritrasmettere |
| Annotazione e loghi nella diretta | Disegna barra, orologio e loghi sul video |

![La pagina Stream: chiave, risoluzione, destinazioni aggiuntive, overlay e le impostazioni della diretta automatica.](img/ui-config-stream.png){ width=100% }

Nelle schede per fase del giorno si impostano frequenza dei fotogrammi (`framerate`), guadagno, bilanciamento del bianco, riduzione del rumore e nitidezza: di notte conviene un framerate basso (4–5) e un guadagno alto, di giorno il contrario.

Il bilanciamento del bianco funziona come per lo scatto, modalità *Manuale* compresa: sotto le luci al sodio è il modo per evitare che la diretta viri all'arancione. Vedi il capitolo *La cattura delle immagini*.

Bitrate e buffer (`bitrate`, `buffer`) governano la qualità: 4000–4500 kbit/s per il 1440p sono un punto di partenza sensato. La codifica usa il preset `veryfast` e un gruppo di immagini pari a due secondi, come richiesto dalle piattaforme di live.

## Ritrasmissione su più destinazioni

Nel campo *Destinazioni aggiuntive* si elencano altri URL RTMP completi, uno per riga: Twitch, un server proprio, un'altra piattaforma. Il video viene codificato **una sola volta** e semplicemente duplicato verso tutte le uscite, quindi il carico sulla CPU non cambia con il numero di destinazioni.

Una destinazione irraggiungibile non trascina giù le altre: viene ignorata per quella sessione di streaming.

## La diretta automatica su YouTube

La sola chiave di streaming non manda in onda nulla: YouTube ha ritirato lo "Stream now", e senza un *broadcast* collegato i dati arrivano ma restano invisibili finché qualcuno non apre la Live Control Room. zeroCAM crea e collega il broadcast da sé, via YouTube Data API.

### Credenziali

1. Sulla [Google Cloud Console](https://console.cloud.google.com/) creare un progetto e abilitare **YouTube Data API v3**.
2. Configurare la schermata di consenso OAuth (utenti **Esterni**) e portarne lo stato di pubblicazione su **In produzione**. Lasciandola in *Testing* Google fa scadere i refresh token dopo sette giorni e la diretta smette di partire dopo una settimana. L'app non ha bisogno di essere verificata: l'avviso "app non verificata" compare solo durante l'autorizzazione.
3. Creare credenziali OAuth di tipo **TV e dispositivi di immissione limitata** e annotare **Client ID** e **Client Secret**. Il tipo conta: il device flow usato dall'interfaccia rifiuta un client desktop.
4. In **Configuration → Stream → Diretta automatica** incollare Client ID e Client Secret e premere **Autentica**. Compare un codice da inserire su [google.com/device](https://www.google.com/device), da qualsiasi dispositivo: telefono, tablet o PC. Autorizzando si sceglie anche il canale su cui pubblicare, che per un account Brand va selezionato proprio lì.
5. Il **Refresh Token** viene compilato da solo appena l'autorizzazione è concessa, e l'interfaccia dichiara **su quale canale** ci si è autenticati: deve essere lo stesso da cui proviene la chiave di streaming, altrimenti il primo scatto fallisce con `The user is not enabled for live streaming`. Attivare *Auto broadcast* e salvare.

Il canale deve avere le dirette abilitate su [youtube.com/features](https://www.youtube.com/features): serve la verifica del numero di telefono e la prima attivazione può richiedere fino a 24 ore.

L'autenticazione dall'interfaccia funziona anche raggiungendo la webcam in http sulla LAN, senza HTTPS né redirect: è il metodo consigliato, perché il Pi non ha un browser e un client desktop lo pretenderebbe sulla stessa macchina. Da un PC con browser resta comunque disponibile `installation_tools/yt_oauth_setup.py`, che però richiede un client OAuth di tipo *Applicazione desktop*.

Le stesse credenziali servono al caricamento del timelapse: il token ottenuto con *Autentica* copre già anche quello.

Cambiando progetto sulla Cloud Console il refresh token va rigenerato, perché è legato al client ID: la chiave di streaming invece non cambia, appartiene al canale YouTube e non al progetto.

### Impostazioni del broadcast

| Campo | Significato |
|---|---|
| Titolo diretta | Accetta i segnaposto `{date}` e `{time}` |
| Descrizione | Testo della diretta |
| Privacy | Pubblico, non in elenco o privato |
| Latenza | Normale, bassa o molto bassa |
| Timeout API | Attesa massima per le chiamate a YouTube |
| DVR, Registra dall'inizio | Opzioni di registrazione della diretta |
| Contenuto per bambini | Dichiarazione richiesta da YouTube |
| Chiudi diretta allo shutdown | Termina il broadcast quando l'applicazione si arresta |
| Nuova diretta alle (HH:MM) | Ricambio giornaliero del broadcast |

Il broadcast viene creato con avvio automatico e senza interruzione automatica: va in onda da solo appena ffmpeg comincia a pubblicare e sopravvive alle pause per la cattura. Il monitor stream è disattivato, altrimenti l'avvio automatico porterebbe la diretta in "testing" invece che in onda.

### Riuso e ricambio

Prima di ogni ripartenza dello streaming il software cerca un broadcast già collegato alla stream key e in stato `active` o `upcoming`, e lo riusa. Ne crea uno nuovo solo quando non ne trova, cosa che accade tipicamente quando YouTube chiude la diretta al limite delle 12 ore.

Il campo **Nuova diretta alle (HH:MM)** forza invece un ricambio quotidiano: al primo scatto successivo a quell'ora la diretta in corso viene chiusa e ne parte una nuova, con il titolo rivalutato dai segnaposto. Impostandolo a `00:00` si ottiene una diretta al giorno, con la data corretta nel titolo. Lasciando il campo vuoto il comportamento resta quello precedente: il campo è vuoto anche nelle installazioni nuove, quindi il ricambio va abilitato esplicitamente.

Ogni volta che una diretta viene riusata il log dice perché non è stata sostituita, così è immediato capire se il ricambio è attivo:

```
Reusing YouTube broadcast Xy1z2 (daily reset not configured).
Reusing YouTube broadcast Xy1z2 (started after the daily reset of 27/07/2026 00:00).
```

## Anteprima nell'interfaccia

Mentre lo streaming è attivo, in **Cam Control** compare l'interruttore **Anteprima diretta**: mostra un fotogramma al secondo preso dal flusso video al posto dell'ultimo scatto. È lo stesso fotogramma che alimenta ONVIF, con le maschere privacy già applicate, scritto su tmpfs per non consumare la microSD.

![Anteprima attiva: l'immagine viene dal flusso video e il disegno delle maschere è disabilitato.](img/ui-cam-control-anteprima.png){ width=100% }

L'interruttore compare solo se il fotogramma è recente: nei secondi in cui lo streaming è fermo per lo scatto l'anteprima torna da sola all'ultima immagine.

## Verifiche e diagnosi

All'avvio dello streaming il log riporta destinazioni, maschere preparate e, se attivo, l'overlay:

```
Restreaming to 2 destinations: a.rtmp.youtube.com, live.twitch.tv
Frame privacy masks ready for 2560x1440: 2 blurred, 1 filled.
Stream overlay 'Logo' at 2171,6 scaled to 227px wide.
Reusing YouTube broadcast xxxxxxxx.
```

Se ffmpeg si chiude in modo anomalo compare `Broken pipe with ffmpeg, stopping stream.`: lo streaming riparte al ciclo successivo. Se il messaggio si ripete a ogni ciclo, la causa è quasi sempre nella riga di comando di ffmpeg — chiave di streaming errata, destinazione aggiuntiva malformata o filtro non disponibile nel build di ffmpeg installato.
