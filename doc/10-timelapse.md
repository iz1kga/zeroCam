# Timelapse settimanale

## Il principio

Ogni scatto lascia una copia ridimensionata in `data/timelapse_frames/`. Una volta a settimana i fotogrammi vengono montati con ffmpeg e il video caricato sul canale YouTube. L'archivio di diagnosi degli scatti è un'altra cosa e non partecipa.

I fotogrammi sono salvati già alla risoluzione finale del video: il montaggio è più rapido e lo spazio occupato è prevedibile. Il fotogramma è l'immagine definitiva — ritagliata, mascherata e annotata — quindi il video mostra esattamente ciò che è stato pubblicato.

### I metadati dei fotogrammi

Ogni fotogramma porta gli EXIF della cattura da cui proviene:

| Campo | Contenuto |
|---|---|
| Data e ora | Istante dello scatto |
| Tempo di esposizione | Quello effettivo, anche i secondi delle pose notturne |
| ISO | Ricavato dal guadagno analogico (guadagno 8 → ISO 800) |
| Bilanciamento del bianco | Automatico o manuale |
| Descrizione | Nome della webcam, fase del giorno e riassunto dei dati di scatto |
| Commento utente | Tutti i metadati di libcamera in JSON |

L'ultima riga è quella che serve davvero per il bilanciamento del bianco: contiene `ColourGains`, cioè i guadagni di rosso e blu che l'automatismo ha scelto in quel momento, insieme a temperatura colore, luminosità in lux e temperatura del sensore. Sono i numeri da riportare nei campi manuali della pagina Camera quando l'automatico sbaglia. Si leggono con `exiftool`, con `exiv2` o da qualunque libreria; il riassunto in chiaro nella descrizione basta per un colpo d'occhio.

I fotogrammi già archiviati prima di questa versione restano senza metadati: l'informazione non è più recuperabile, perché nasce con la cattura.

## Configurazione

**Configuration → Timelapse**

| Campo | Significato |
|---|---|
| Timelapse attivo | Attiva raccolta, montaggio e pubblicazione |
| Giorno, Ora | Quando eseguire il montaggio settimanale |
| Conserva i frame (settimane) | Età oltre la quale i fotogrammi vengono cancellati |
| Larghezza (px) | Larghezza dei fotogrammi, e quindi del video |
| Qualità JPEG | Qualità di compressione dei fotogrammi |
| Minimo per montare | Sotto questo numero di fotogrammi il montaggio non parte |
| FPS | Fotogrammi al secondo del video finale |
| CRF | Qualità della codifica: più basso, più qualità e più peso |
| Preset x264 | Compromesso fra velocità e compressione |
| Thread | Core impiegati dalla codifica |
| Tieni il file sul Pi | Conserva il video montato in `data/timelapse/` |
| Titolo, Descrizione | Testi del video, con segnaposto |
| Privacy, Contenuto per bambini | Impostazioni di pubblicazione su YouTube |

![La pagina Timelapse della configurazione: pianificazione, fotogrammi, parametri del video e brano di sottofondo.](img/ui-config-timelapse.png){ width=100% }

Nei testi si possono usare `{from}`, `{to}`, `{date}` e `{frames}`, sostituiti rispettivamente con la data del primo e dell'ultimo fotogramma, la data del montaggio e il numero di fotogrammi.

Il montaggio gira con priorità bassa (`nice 19`) per non disturbare lo streaming: preset e numero di thread regolano quanto pesa sulla CPU. Su un Pi 5, `medium` con 2 thread è un buon compromesso.

## Audio

Il video è muto se non si sceglie un brano in *Audio → Brano di sottofondo*, fra quelli caricati in **Configuration → Assets**. Il brano viene ripetuto fino alla fine dei fotogrammi e tagliato lì, quindi non serve che duri quanto il video: un minuto di musica copre un timelapse di qualsiasi lunghezza. Il *Volume* lo attenua in percentuale.

Vale l'avvertenza dei diritti già vista per la diretta, con un aggravante: un video caricato con musica protetta può essere rivendicato subito, e la rivendicazione resta attaccata al video pubblicato.

## Pianificazione

Il montaggio parte nel giorno e all'ora impostati. Indipendentemente da esso, ogni giorno alle 04:30 gira una pulizia che elimina i fotogrammi più vecchi della finestra di conservazione: se il montaggio fallisce per settimane, i fotogrammi non si accumulano senza limite.

Cambiando giorno, ora o abilitazione, la pianificazione viene ricostruita al salvataggio: non serve riavviare. Insieme a essa riparte anche il conteggio dell'intervallo di scatto, quindi la foto successiva arriva dopo un intervallo intero.

## Spazio su disco

È l'aspetto che sorprende di più. Con uno scatto ogni 10 minuti a 2560 pixel di larghezza si producono circa 144 fotogrammi al giorno, dell'ordine del gigabyte al mese. Con quattro settimane di conservazione l'occupazione si stabilizza intorno al gigabyte.

Per ridurla si può abbassare la larghezza dei fotogrammi, la qualità JPEG, o accorciare la finestra di conservazione. La pagina **Timelapse** mostra sempre quanti fotogrammi ci sono e quanto occupano.

## Montaggio a comando

I pulsanti in fondo alla pagina Timelapse:

* **Genera e pubblica ora** — monta e carica subito, senza attendere la scadenza settimanale;
* **Genera senza pubblicare** — monta soltanto, utile per controllare il risultato prima di renderlo pubblico;
* **Aggiorna** — rilegge lo stato.

Il montaggio dura diversi minuti e prosegue in background: l'esito compare nel riquadro *Stato*, con il numero di fotogrammi usati e il collegamento al video su YouTube.

## Galleria

Nella stessa pagina una galleria permette di scorrere i fotogrammi raccolti: si sceglie il giorno, si scorre con il cursore o con le frecce, e il pulsante *Riproduci* fa un'anteprima animata a 2, 5 o 10 fotogrammi al secondo.

![La galleria: scelta del giorno, cursore, comandi di riproduzione e velocità.](img/ui-timelapse-galleria.png){ width=100% }

La riproduzione avanza solo quando l'immagine successiva è arrivata dal dispositivo: alla prima passata può risultare più lenta della velocità scelta, poi i fotogrammi restano nella cache del browser e scorrono fluidi. È il modo più rapido per accorgersi di una giornata di fotogrammi rovinati prima di montare il video.

## Caricamento su YouTube

Il video viene caricato con le stesse credenziali OAuth della diretta, in modalità *resumable* a blocchi da 8 MiB: un'interruzione di rete non costringe a ricominciare da capo. Il token ottenuto con il pulsante *Autentica* copre già il caricamento; un refresh token generato con le prime versioni dello script di setup, prima che questa funzione esistesse, va rigenerato una volta.

Se *Tieni il file sul Pi* è disattivo, il video viene rimosso dopo il caricamento riuscito.
