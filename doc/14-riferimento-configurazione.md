# Riferimento della configurazione

Tutte le chiavi di `/usr/local/zerocam/data/.conf.json`. I campi marcati **cifrato** sono salvati con il prefisso `enc:` e derivano da `ZEROCAM_SECRET_KEY`.

## deviceDetails

| Chiave | Tipo | Significato |
|---|---|---|
| `name` | testo | Nome della webcam |
| `latitude`, `longitude` | numero | Coordinate decimali |
| `elevation` | numero | Quota in metri |
| `sunRiseOffset`, `sunSetOffset` | numero | Elevazione solare (gradi) di inizio e fine della fase `day` |
| `dawnOffset`, `duskOffset` | numero | Elevazione solare (gradi) di inizio `dawn` e fine `dusk` |
| `hflip`, `vflip` | sì/no | Ribaltamento dell'immagine |

## security

| Chiave | Tipo | Significato |
|---|---|---|
| `username` | testo | Utente dell'interfaccia (`admin`) |
| `password` | hash | Password dell'interfaccia |
| `flask_secret_key` | testo | Chiave di sessione, generata al primo avvio |

## cameraParameters

| Chiave | Tipo | Significato |
|---|---|---|
| `type` | testo | `piCamera` oppure `fakeCamera` |
| `shotInterval` | numero | Secondi fra gli scatti |
| `crop.enabled` | sì/no | Attiva il ritaglio |
| `crop.width`, `crop.height` | numero | Dimensioni del ritaglio in pixel |
| `crop.x_offset`, `crop.y_offset` | numero | Spostamento rispetto al centro |
| `dawn`, `day`, `dusk`, `night` | oggetto | Parametri per fase (sotto) |

Le tre chiavi seguenti servono a diagnosi e sviluppo, non hanno campo nell'interfaccia e in esercizio restano spente:

| Chiave | Tipo | Significato |
|---|---|---|
| `hardResetInterval` | numero | Scatti fra un reset completo della camera e il successivo (0 = mai) |
| `archiveImages` | sì/no | Conserva ogni scatto in `data/images/` con i metadati della cattura |
| `unsharpMask` | sì/no | Applica una maschera di contrasto all'immagine |

Parametri per fase, fase `day`:

| Chiave | Significato |
|---|---|
| `AeEnable` | Esposizione automatica |
| `AeMeteringMode` | Misurazione: centrata, spot, matrix |
| `AwbMode` | Modalità di bilanciamento del bianco (vedi sotto) |
| `ColourGainRed`, `ColourGainBlue` | Guadagni fissi di rosso e blu, usati solo con `AwbMode` a 7 |
| `HdrMode` | HDR: off, singola esposizione, multipla |
| `AnalogueGain`, `ExposureTime`, `ExposureValue` | Valori di partenza |
| `NoiseReductionMode`, `Sharpness` | Riduzione rumore e nitidezza |

Parametri per fase, fasi `dawn`, `dusk`, `night`:

| Chiave | Significato |
|---|---|
| `MinTargetBrightness`, `MaxTargetBrightness` | Intervallo di luminosità media cercato (0–255) |
| `AwbMode`, `ColourGainRed`, `ColourGainBlue` | Bilanciamento del bianco, come sopra |
| `NoiseReductionMode`, `Sharpness` | Come sopra |

I valori di `AwbMode` sono quelli di libcamera:

| Valore | Modalità |
|---:|---|
| 0 | Auto |
| 1 | Incandescent |
| 2 | Tungsten |
| 3 | Fluorescent |
| 4 | Indoor |
| 5 | Daylight |
| 6 | Cloudy |
| 7 | Manuale: AWB spento, valgono `ColourGainRed` e `ColourGainBlue` |

## streamParameters

| Chiave | Tipo | Significato |
|---|---|---|
| `enabled` | sì/no | Attiva lo streaming |
| `yt_api_key` | testo **cifrato** | Chiave di streaming YouTube |
| `width`, `height` | numero | Risoluzione del video |
| `bitrate`, `buffer` | testo | Per esempio `4000k` e `8000k` |
| `extra_destinations` | elenco | Altri URL RTMP |
| `overlay` | sì/no | Annotazione e loghi sul video |
| `dawn`, `day`, `dusk`, `night` | oggetto | `framerate`, `AnalogueGain`, `AwbMode`, `ColourGainRed`, `ColourGainBlue`, `NoiseReductionMode`, `Sharpness` |

## youtubeLive

| Chiave | Tipo | Significato |
|---|---|---|
| `enabled` | sì/no | Crea e collega il broadcast via API |
| `client_id` | testo | Client ID OAuth |
| `client_secret` | testo **cifrato** | Client Secret OAuth |
| `refresh_token` | testo **cifrato** | Refresh token OAuth |
| `title`, `description` | testo | Testi della diretta; `{date}` e `{time}` |
| `privacy` | testo | `public`, `unlisted`, `private` |
| `latency` | testo | `normal`, `low`, `ultraLow` |
| `dvr`, `record` | sì/no | Opzioni di registrazione |
| `made_for_kids` | sì/no | Dichiarazione richiesta da YouTube |
| `end_on_shutdown` | sì/no | Chiude la diretta all'arresto dell'applicazione |
| `daily_reset_time` | testo | `HH:MM` per il ricambio giornaliero; vuoto = disattivo |
| `timeout` | numero | Secondi di attesa per le chiamate API |

## timelapse

| Chiave | Tipo | Significato |
|---|---|---|
| `enabled` | sì/no | Attiva raccolta e pubblicazione |
| `day`, `time` | testo | Giorno (`monday`…) e ora `HH:MM` del montaggio |
| `frame_width`, `frame_quality` | numero | Dimensione e qualità dei fotogrammi |
| `fps`, `crf`, `preset`, `threads`, `nice` | vari | Parametri di codifica |
| `min_frames` | numero | Soglia sotto la quale non si monta |
| `retention_weeks` | numero | Settimane di conservazione dei fotogrammi |
| `keep_local` | sì/no | Conserva il video sul dispositivo |
| `frames_dir`, `output_dir` | testo | Percorsi; se relativi sono risolti dentro la cartella dei dati |
| `title`, `description` | testo | Testi del video; `{from}`, `{to}`, `{date}`, `{frames}` |
| `privacy`, `made_for_kids` | vari | Impostazioni di pubblicazione |

## Annotation

| Chiave | Tipo | Significato |
|---|---|---|
| `Container.R/G/B/A` | numero | Colore e trasparenza della fascia |
| `Container.Offset` | numero | Margine, e quindi altezza della fascia |
| `Content.Text` | testo | Testo fisso |
| `Content.FontSize` | numero | Corpo del carattere |
| `Content.Color.R/G/B/A` | numero | Colore del testo |
| `DTFormat` | testo | Formato `strftime` della data |

## OverlayImages

Elenco di oggetti:

| Chiave | Tipo | Significato |
|---|---|---|
| `enabled` | sì/no | Attiva il logo |
| `name` | testo | Etichetta per il log |
| `url` | testo | Indirizzo dell'immagine |
| `X`, `Y` | numero | Posizione in pixel sull'immagine finale |
| `scale` | numero | Percentuale; valori oltre 100 non ingrandiscono |
| `opacity` | numero | Percentuale, moltiplicata per la trasparenza del PNG |

## FtpHost

| Chiave | Tipo | Significato |
|---|---|---|
| `host`, `port` | testo, numero | Server FTP |
| `username` | testo | Utente |
| `password` | testo **cifrato** | Password |
| `folder`, `filename` | testo | Cartella e nome del file remoto |
| `timeout` | numero | Secondi |

## HttpUploader

| Chiave | Tipo | Significato |
|---|---|---|
| `enabled` | sì/no | Attiva l'invio |
| `url` | testo | Endpoint |
| `token` | testo **cifrato** | Bearer token |
| `timeout` | numero | Secondi |
| `send_timestamp` | sì/no | Aggiunge l'istante dello scatto |

## onvif

| Chiave | Tipo | Significato |
|---|---|---|
| `enabled` | sì/no | Attiva il servizio |
| `onvif_w` | numero | Larghezza dell'istantanea |
| `username`, `password` | testo | Credenziali (password **cifrata**) |
| `allow_unsecure` | sì/no | Consente `/snapshot.jpg` senza autenticazione |

## settingsManager

| Chiave | Tipo | Significato |
|---|---|---|
| `port` | numero | Porta dell'interfaccia web (default 8080) |
