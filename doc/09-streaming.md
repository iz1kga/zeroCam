# Streaming in diretta

## Come funziona

Il Raspberry Pi produce fotogrammi grezzi che ffmpeg codifica in H.264 e spinge via RTMP verso YouTube — e, se richiesto, verso altre destinazioni. All'audio provvede una traccia silenziosa generata da ffmpeg, necessaria perché YouTube accetti il flusso.

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

Nelle schede per fase del giorno si impostano frequenza dei fotogrammi (`framerate`), guadagno, bilanciamento del bianco, riduzione del rumore e nitidezza: di notte conviene un framerate basso (4–5) e un guadagno alto, di giorno il contrario.

Bitrate e buffer (`bitrate`, `buffer`) governano la qualità: 4000–4500 kbit/s per il 1440p sono un punto di partenza sensato. La codifica usa il preset `veryfast` e un gruppo di immagini pari a due secondi, come richiesto dalle piattaforme di live.

## Ritrasmissione su più destinazioni

Nel campo *Destinazioni aggiuntive* si elencano altri URL RTMP completi, uno per riga: Twitch, un server proprio, un'altra piattaforma. Il video viene codificato **una sola volta** e semplicemente duplicato verso tutte le uscite, quindi il carico sulla CPU non cambia con il numero di destinazioni.

Una destinazione irraggiungibile non trascina giù le altre: viene ignorata per quella sessione di streaming.

## La diretta automatica su YouTube

La sola chiave di streaming non manda in onda nulla: YouTube ha ritirato lo "Stream now", e senza un *broadcast* collegato i dati arrivano ma restano invisibili finché qualcuno non apre la Live Control Room. zeroCAM crea e collega il broadcast da sé, via YouTube Data API.

### Credenziali

1. Sulla [Google Cloud Console](https://console.cloud.google.com/) creare un progetto, abilitare **YouTube Data API v3**, configurare la schermata di consenso OAuth e creare credenziali OAuth di tipo **Applicazione desktop**.
2. Su un PC con browser eseguire lo script incluso nell'applicazione:

   ```bash
   python3 installation_tools/yt_oauth_setup.py
   ```

   Inserire Client ID e Client Secret, autorizzare l'accesso e annotare il **refresh token** stampato.
3. In **Configuration → Stream → Diretta automatica** attivare *Auto broadcast* e incollare i tre valori.

Le stesse credenziali servono anche al caricamento del timelapse, che richiede però anche l'ambito `youtube.upload`: se il refresh token è stato generato prima di quella funzione, va rigenerato.

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

Il campo **Nuova diretta alle (HH:MM)** forza invece un ricambio quotidiano: al primo scatto successivo a quell'ora la diretta in corso viene chiusa e ne parte una nuova, con il titolo rivalutato dai segnaposto. Impostandolo a `00:00` si ottiene una diretta al giorno, con la data corretta nel titolo. Lasciando il campo vuoto il comportamento resta quello precedente.

## Anteprima nell'interfaccia

Mentre lo streaming è attivo, in **Cam Control** compare l'interruttore **Anteprima diretta**: mostra un fotogramma al secondo preso dal flusso video al posto dell'ultimo scatto. È lo stesso fotogramma che alimenta ONVIF, con le maschere privacy già applicate, scritto su tmpfs per non consumare la microSD.

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
