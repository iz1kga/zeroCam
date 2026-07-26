# Annotazione e loghi

## La barra di annotazione

**Configuration → Annotation** definisce la fascia che compare in fondo all'immagine, con un testo libero a sinistra e la data/ora a destra.

| Campo | Significato |
|---|---|
| Container R, G, B, A | Colore e trasparenza della fascia (0–255; A a 0 la rende invisibile) |
| Container Offset | Margine in pixel fra testo e bordi; determina anche l'altezza della fascia |
| Text R, G, B, A | Colore del testo |
| Text Content | Testo fisso, tipicamente nome della località e indirizzo del sito |
| Font Size | Corpo del carattere in pixel |
| Date/Time Format | Formato della data, con i codici `strftime` |

![La pagina Annotation: colori della fascia, colore e corpo del testo, formato della data.](img/ui-config-annotation.png){ width=100% }

L'altezza della fascia è calcolata come corpo del carattere più due volte l'offset: per una barra più alta si aumenta l'offset, per un testo più grande il corpo.

Formati di data più comuni:

| Formato | Risultato |
|---|---|
| `%d-%m-%Y %H:%M` | `26-07-2026 19:21` |
| `%d/%m/%Y %H:%M:%S` | `26/07/2026 19:21:04` |
| `%A %d %B %Y` | nome del giorno e del mese, secondo la lingua di sistema |

Il carattere usato è `static/css/fonts/Arial.ttf`, incluso nell'applicazione.

![Uno scatto pubblicato: barra con testo a sinistra e data/ora a destra, logo in alto a destra.](img/foto-annotata.png){ width=100% }

## I loghi

**Configuration → Overlays** gestisce un elenco di immagini da sovrapporre, ciascuna con:

| Campo | Significato |
|---|---|
| Enabled | Attiva o disattiva il singolo logo |
| Name | Etichetta, compare solo nel log |
| URL | Indirizzo dell'immagine, tipicamente un PNG con trasparenza |
| X, Y | Posizione dell'angolo superiore sinistro, in pixel dell'immagine finale |
| Scale | Percentuale di ridimensionamento |
| Opacity | Opacità in percentuale |

I loghi vengono scaricati all'avvio dell'applicazione e tenuti in memoria: se si cambia l'immagine all'origine mantenendo lo stesso indirizzo, il nuovo file viene preso al riavvio successivo.

Due comportamenti da conoscere:

* **La scala riduce soltanto.** Un valore superiore a 100 lascia il logo alle sue dimensioni originali: per averlo più grande serve un file sorgente più grande. Vale sia per la foto sia per il video, così le due uscite restano identiche.
* **L'opacità moltiplica la trasparenza del PNG.** Con `opacity: 80` un logo già semitrasparente diventa più tenue; con 100 resta come nel file.

Le coordinate si riferiscono all'immagine finale, cioè dopo il ritaglio. Cambiando le impostazioni di *Crop* i loghi vanno riposizionati.

## Annotazione e loghi sulla diretta

La spunta **Annotazione e loghi nella diretta**, in **Configuration → Stream**, riporta gli stessi elementi sul video trasmesso. Non c'è una seconda configurazione: testo, colori, corpo del carattere, coordinate e scala sono quelli della foto, riscalati per il rapporto fra la larghezza dello streaming e quella dello scatto. Un corpo di 50 pixel su una foto da 4056 diventa circa 31 pixel su uno streaming da 2560.

Il disegno lo fa ffmpeg mentre già ricodifica il video, con i filtri `drawbox`, `drawtext` e `overlay`: il costo in CPU è trascurabile e i fotogrammi non passano da Python. L'orologio è aggiornato fotogramma per fotogramma, quindi in diretta scorre davvero invece di restare fermo all'ora di avvio dello streaming.

Poiché il comando di ffmpeg si costruisce all'avvio dello streaming, l'attivazione ha effetto **al riavvio dello stream**, cioè dopo lo scatto successivo.

> **Requisito** — il filtro `drawtext` richiede un ffmpeg compilato con libfreetype. Sui pacchetti di Raspberry Pi OS c'è; per verificarlo: `ffmpeg -filters | grep drawtext`.

Un'ultima differenza da tenere presente: se lo streaming inquadra una porzione di sensore diversa da quella della foto, la posizione dei loghi può risultare spostata di qualche pixel rispetto allo scatto. Le coordinate vengono riscalate, non riproiettate come accade invece per le maschere privacy.
