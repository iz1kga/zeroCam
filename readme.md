# 📸 zeroCAM - By IZ1KGA

## Versione Italiana
---

ZeroCam è un progetto per costruire una webcam paesaggistica ad alte prestazioni utilizzando un Raspberry Pi (consigliato Pi 5) e una PiCamera HQ.

Grazie al sensore della PiCamera HQ, il sistema cattura immagini e video di qualità eccezionale, superando le webcam tradizionali, con ottime performance anche in condizioni di scarsa illuminazione.

Funzionalità principali:

Immagini di Alta Qualità: Scatta foto nitide e dettagliate, anche di notte.

Scatti Automatici e Upload FTP: Cattura immagini a intervalli regolari e le carica automaticamente su un server FTP.

Streaming Live su YouTube: Trasmette un flusso video in diretta sul tuo canale YouTube.
---

## 🚀 Guida all'Installazione

### Installazione Automatizzata (Consigliata)

Il metodo raccomandato per installare zeroCAM è utilizzare lo script di installazione fornito. Lo script si occuperà di tutti i passaggi necessari, tra cui l'installazione delle dipendenze, la configurazione dell'applicazione e l'impostazione di un servizio di sistema per l'avvio automatico.

**Istruzioni:**

1.  Scarica ed esegui lo script con un unico comando:
    ```bash
    wget -O zeroCamInstall https://www.iz1kga.it/zeroCam/zeroCamInstall && sudo bash zeroCamInstall
    ```
2.  Segui le istruzioni a schermo. Ti verrà chiesto di inserire la versione di zeroCAM da installare e di impostare una password per l'amministratore.

### Primo Accesso

Una volta completata l'installazione, puoi accedere all'interfaccia web del dispositivo:

* **URL:** `http://<IP_DEL_TUO_RASPBERRY>:8080/`
* **Username:** `admin`
* **Password:** Quella che hai fornito durante l'installazione.

Ora puoi configurare la tua telecamera e iniziare a usarla!

### Dove stanno i dati

L'installazione è divisa in due cartelle:

```
/usr/local/zerocam/app     codice, cancellato e riscritto a ogni aggiornamento
/usr/local/zerocam/data    configurazione, .env, log, fotogrammi, immagini
```

L'installer rimuove `app/` prima di estrarre la nuova versione: tutto ciò che deve sopravvivere sta in `data/`, che non viene mai toccata. Ci trovi `.conf.json`, `.privacy_mask.json`, `.env`, `.capture_info`, `logs/`, `images/`, `timelapse_frames/` e `timelapse/`.

Chi aggiorna da una versione precedente non deve fare nulla: l'installer sposta i file rimasti in `app/` prima di rimuoverla, e al primo avvio l'applicazione fa lo stesso controllo per sicurezza, scrivendolo nel log. I percorsi relativi rimasti in configurazione (per esempio `./timelapse_frames`) vengono risolti dentro `data/`; quelli assoluti restano dove sono, quindi si possono ancora tenere i fotogrammi su un disco esterno. `ZEROCAM_DATA_DIR` permette di spostare l'intera cartella dei dati altrove.

### Diretta YouTube automatica

Il push RTMP da solo non basta più: YouTube ha ritirato lo "Stream now", quindi la sola chiave di streaming non fa andare in onda nulla finché non si apre la Live Control Room. zeroCAM può creare e collegare il broadcast da solo, con avvio automatico e senza interruzione automatica, così la diretta parte da sé e sopravvive alle pause di pochi secondi durante la cattura della foto.

1.  Sulla [Google Cloud Console](https://console.cloud.google.com/): crea un progetto, abilita **YouTube Data API v3**, configura la schermata di consenso OAuth e crea credenziali OAuth di tipo **Applicazione desktop**.
2.  Su un PC con browser esegui lo script di setup (serve solo Python e `requests`):
    ```bash
    python3 installation_tools/yt_oauth_setup.py
    ```
    Inserisci Client ID e Client Secret, autorizza l'accesso e annota il **refresh token** stampato.
3.  Nell'interfaccia web, pagina **Config → YouTube Live**: attiva *Auto broadcast* e incolla Client ID, Client Secret e Refresh Token. La stream key resta quella di **Stream Parameters**.

Nel titolo della diretta puoi usare i segnaposto `{date}` e `{time}`. Il broadcast viene riusato finché resta valido e ricreato automaticamente quando YouTube lo chiude (limite di 12 ore).

Il campo **Nuova diretta alle (HH:MM)** forza il ricambio giornaliero: se valorizzato (es. `00:00`), al primo scatto successivo a quell'ora la diretta in corso viene chiusa e ne parte una nuova, con titolo aggiornato dai segnaposto. Lasciandolo vuoto il comportamento resta quello precedente (ricambio solo quando YouTube chiude la diretta).

### Ritrasmissione su più destinazioni

In **Config → Stream**, nel campo *Destinazioni aggiuntive*, puoi elencare altri URL RTMP (uno per riga) verso cui inviare lo stesso flusso: Twitch, un server tuo, un'altra piattaforma. Il video viene codificato una volta sola e semplicemente duplicato, quindi il carico sulla CPU non cambia. Una destinazione irraggiungibile non interrompe le altre.

### Annotazione e loghi nella diretta

La spunta *Annotazione e loghi nella diretta*, sempre in **Config → Stream**, riporta sul video in diretta la barra con testo e data/ora della pagina **Annotation** e i loghi abilitati in **Overlay Images**. Non c'è una seconda configurazione da compilare: font, coordinate e scala sono quelli della foto, riscalati per il rapporto fra la larghezza dello streaming e quella dello scatto.

Il disegno lo fa ffmpeg con i suoi filtri mentre già ricodifica, quindi il costo in CPU è trascurabile e i frame non passano da Python. L'orologio è aggiornato fotogramma per fotogramma, non congelato all'avvio della diretta, e i loghi vengono scaricati una volta sola e tenuti in cache. Le privacy mask restano applicate prima, quindi testo e loghi non finiscono mai sotto la sfocatura.

Il campo *opacity* dei loghi vale per entrambi: moltiplica la trasparenza del PNG sia sullo scatto sia in diretta. Anche la scala si comporta allo stesso modo nei due casi, cioè riduce e basta: valori sopra il 100% lasciano il logo alla sua dimensione originale.

Se lo streaming inquadra una porzione di sensore diversa dalla foto, la posizione dei loghi può risultare spostata di qualche pixel rispetto allo scatto: le coordinate sono riscalate, non riproiettate.

### Timelapse settimanale

Ogni scatto lascia una copia ridimensionata in una cartella dedicata (`timelapse_frames/`); una volta a settimana i fotogrammi vengono montati con ffmpeg e il video caricato sul canale YouTube. L'archivio di debug (*Camera → Archive Images*) è un'altra cosa e non serve a questo.

Si configura in **Config → Timelapse**: giorno e ora del montaggio, fps, risoluzione dei fotogrammi, qualità di codifica, titolo e privacy del video. Nel titolo e nella descrizione sono disponibili i segnaposto `{from}`, `{to}`, `{date}` e `{frames}`.

Due note pratiche:

* Le credenziali sono le stesse della diretta, ma serve anche lo scope `youtube.upload`. Se il refresh token è stato generato prima di questa funzione, va rigenerato con `yt_oauth_setup.py`.
* I fotogrammi occupano spazio: con uno scatto ogni 10 minuti a 2560px si va sull'ordine del gigabyte al mese. Il parametro *Conserva i frame* cancella automaticamente quelli più vecchi, e la pagina Timelapse mostra sempre quanti sono e quanto occupano.

Il pulsante *Genera e pubblica ora* monta subito il timelapse senza aspettare la scadenza settimanale, utile per provare la configurazione.

Nella stessa pagina c'è una galleria per scorrere i fotogrammi raccolti: si sceglie il giorno, si scorre con il cursore o con le frecce, e il pulsante *Riproduci* fa un'anteprima animata a 2, 5 o 10 fotogrammi al secondo. È il modo più rapido per controllare cosa finirà nel video prima di montarlo.

### Backup e ripristino della configurazione

Nella pagina **Sicurezza** si può scaricare l'intera configurazione (privacy mask compresa) in un unico file JSON e reimportarla in caso di SD morta o reinstallazione.

Sul dispositivo i segreti sono cifrati con `ZEROCAM_SECRET_KEY`, che vive nell'ambiente del servizio: copiare il `.conf.json` così com'è darebbe un backup illeggibile su un'installazione nuova. Il backup viene quindi costruito dalla configurazione decifrata e richiuso subito con una **passphrase scelta al momento del download** (PBKDF2-SHA256 + Fernet, salt casuale): il file non contiene nulla in chiaro ed è ripristinabile su qualsiasi dispositivo, anche con secret key diversa. La passphrase non è recuperabile: se si perde, il backup è carta straccia.

Il ripristino chiede file e passphrase, riscrive la configurazione ricifrando i segreti con la chiave locale e sovrascrive la privacy mask. Restano esclusi password di accesso all'interfaccia e chiave di sessione Flask, che rimangono quelle del dispositivo su cui si ripristina: un backup vecchio non rimette in uso credenziali di login superate. Conviene riavviare dalla pagina Controllo per applicare tutto.

---

## 📜 Licenza

zeroCAM è rilasciato sotto un modello a doppia licenza.

### Uso Non Commerciale

Per scopi personali, educativi, di ricerca e per qualsiasi altro uso non commerciale, sei libero di utilizzare, modificare e distribuire questo software secondo i termini della licenza [Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International (CC BY-NC-SA 4.0)](https://creativecommons.org/licenses/by-nc-sa/4.0/).

### Uso Commerciale

Se desideri utilizzare questo software per qualsiasi scopo commerciale, è necessario acquistare una licenza. Per informazioni **iz1kga (at) gmail.com**.

---
QUESTO SOFTWARE È FORNITO "COSÌ COM'È", SENZA GARANZIA DI ALCUN TIPO, ESPLICITA O IMPLICITA, INCLUSE, MA NON LIMITATE A, LE GARANZIE DI COMMERCIABILITÀ, IDONEITÀ PER UNO SCOPO PARTICOLARE E NON VIOLAZIONE DI DIRITTI DI TERZI.

IN NESSUN CASO GLI AUTORI O I TITOLARI DEL COPYRIGHT SARANNO RESPONSABILI PER ALCUN RECLAMO, DANNO O ALTRA RESPONSABILITÀ, SIA CHE DERIVI DA UN'AZIONE CONTRATTUALE, ILLECITO CIVILE O ALTRO, DERIVANTE DA, O IN CONNESSIONE CON IL SOFTWARE O L'USO O ALTRE OPERAZIONI RELATIVE AL SOFTWARE. UTILIZZARE A PROPRIO RISCHIO E PERICOLO.

---
---
## English Version
---
ZeroCam is a project for building a high-performance landscape webcam using a Raspberry Pi (Pi 5 recommended) and a PiCamera HQ.

Leveraging the large sensor of the PiCamera HQ, ZeroCam captures stunningly detailed images and video, far surpassing traditional webcams, with excellent performance even in low-light conditions.

Key Features:

High-Quality Imaging: Capture crisp, high-resolution photos, with excellent low-light and night performance.

Automatic Snapshots & FTP Upload: Periodically take pictures and automatically upload them to an FTP server.

YouTube Live Streaming: Broadcast a continuous live feed directly to your YouTube channel.
---

This guide explains how to perform a clean and automated installation of the zeroCAM application on a Debian-based system (like Raspberry Pi OS).

---

## 🚀 Installation Guide

### Automated Installation (Recommended)

The recommended way to install zeroCAM is by using the provided installation script. This script will handle all necessary steps, including installing dependencies, configuring the application, and setting up a system service for automatic startup.

**Instructions:**

1.  Download and run the script with a single command:
    ```bash
    wget -O zeroCamInstall https://www.iz1kga.it/zeroCam/zeroCamInstall && sudo bash zeroCamInstall
    ```
2.  Follow the on-screen instructions. You will be asked to enter the zeroCAM version to install and to set an administrator password.

### First Access

Once the installation is complete, you can access the device's web interface:

* **URL:** `http://<YOUR_RASPBERRY_IP>:8080/`
* **Username:** `admin`
* **Password:** The one you provided during installation.

Now you can configure your camera and start using it!

### Where the data lives

The installation is split in two directories:

```
/usr/local/zerocam/app     code, wiped and rewritten on every upgrade
/usr/local/zerocam/data    configuration, .env, logs, frames, images
```

The installer removes `app/` before extracting the new version, so everything that must survive lives in `data/`, which is never touched: `.conf.json`, `.privacy_mask.json`, `.env`, `.capture_info`, `logs/`, `images/`, `timelapse_frames/` and `timelapse/`.

Upgrading from an earlier version needs no manual step: the installer moves whatever is left in `app/` before removing it, and on the first start the application runs the same check as a safety net, logging what it moves. Relative paths still stored in the configuration (`./timelapse_frames`, for instance) resolve inside `data/`; absolute ones are honoured as they are, so frames can still live on an external disk. `ZEROCAM_DATA_DIR` moves the whole data directory elsewhere.

### Automatic YouTube broadcast

The RTMP push alone is no longer enough: YouTube retired "Stream now", so the stream key by itself never goes on air until someone opens the Live Control Room. zeroCAM can create and bind the broadcast on its own, with auto-start enabled and auto-stop disabled, so the stream goes live by itself and survives the few-second pauses taken to capture the still image.

1.  On the [Google Cloud Console](https://console.cloud.google.com/): create a project, enable **YouTube Data API v3**, configure the OAuth consent screen and create **Desktop app** OAuth credentials.
2.  On a machine with a browser, run the setup script (only Python and `requests` are needed):
    ```bash
    python3 installation_tools/yt_oauth_setup.py
    ```
    Enter Client ID and Client Secret, authorize access and note the printed **refresh token**.
3.  In the web interface, page **Config → YouTube Live**: enable *Auto broadcast* and paste Client ID, Client Secret and Refresh Token. The stream key stays the one in **Stream Parameters**.

The broadcast title supports the `{date}` and `{time}` placeholders. An existing broadcast is reused while valid and recreated automatically once YouTube closes it (12 hour limit).

The **Nuova diretta alle (HH:MM)** field forces a daily rollover: when set (e.g. `00:00`), the first capture after that local time closes the running broadcast and starts a fresh one, with the title placeholders re-evaluated. Leave it empty to keep the previous behaviour (a new broadcast only when YouTube ends the current one).

### Restreaming to several destinations

Under **Config → Stream**, the *Destinazioni aggiuntive* field takes extra RTMP URLs (one per line) to push the same feed to: Twitch, your own server, another platform. The video is encoded once and simply duplicated, so CPU usage does not change. An unreachable destination does not bring the others down.

### Annotation and logos on the live stream

The *Annotazione e loghi nella diretta* checkbox, again under **Config → Stream**, draws the bar with the text and the clock from the **Annotation** page and the logos enabled in **Overlay Images** onto the live video. There is no second configuration to fill in: font, coordinates and scale are the ones used for the still image, rescaled by the ratio between the stream width and the capture width.

The drawing is done by ffmpeg filters while it is already re-encoding, so the CPU cost is negligible and frames never travel through Python for it. The clock updates frame by frame instead of freezing at stream start, and logos are downloaded once and cached. Privacy masks are still applied first, so text and logos never end up under the blur.

The logo *opacity* field applies to both: it multiplies the PNG transparency on the capture as well as on the live feed. Scale behaves the same way in both places too, that is it only shrinks: values above 100% leave the logo at its native size.

If the stream frames a different portion of the sensor than the still image, logo positions can be off by a few pixels compared to the capture: the coordinates are rescaled, not reprojected.

### Weekly timelapse

Every capture leaves a downscaled copy in a dedicated folder (`timelapse_frames/`); once a week the frames are assembled with ffmpeg and the video is uploaded to the YouTube channel. The debug archive (*Camera → Archive Images*) is a different thing and is not involved.

Configure it under **Config → Timelapse**: build day and time, fps, frame resolution, encoding quality, video title and privacy. Title and description accept the `{from}`, `{to}`, `{date}` and `{frames}` placeholders.

Two practical notes:

* Credentials are the same as the live broadcast, but the `youtube.upload` scope is also required. A refresh token generated before this feature must be regenerated with `yt_oauth_setup.py`.
* Frames take space: one capture every 10 minutes at 2560px lands in the order of a gigabyte per month. The *retention* setting removes the oldest ones automatically, and the Timelapse page always shows how many frames there are and how much they take.

The *Genera e pubblica ora* button builds the timelapse immediately instead of waiting for the weekly schedule, which is handy to check the configuration.

The same page holds a gallery to browse the collected frames: pick a day, scrub with the slider or the arrows, and the *Riproduci* button plays an animated preview at 2, 5 or 10 frames per second. It is the quickest way to check what will end up in the video before building it.

### Configuration backup and restore

The **Sicurezza** page downloads the whole configuration (privacy mask included) as a single JSON file and imports it back after a dead SD card or a reinstall.

On the device the secrets are encrypted with `ZEROCAM_SECRET_KEY`, which lives in the service environment: copying `.conf.json` as it is would produce a backup no fresh installation can read. The backup is therefore built from the decrypted configuration and immediately sealed again with a **passphrase chosen at download time** (PBKDF2-SHA256 + Fernet, random salt): nothing travels in clear text and the file restores on any device, even with a different secret key. The passphrase cannot be recovered: lose it and the backup is worthless.

The restore asks for file and passphrase, rewrites the configuration re-encrypting the secrets with the local key, and overwrites the privacy mask. The web login password and the Flask session key are left out and stay those of the device being restored, so an old backup never brings back outdated login credentials. Reboot from the Controllo page afterwards to apply everything.

---

## 📜 License

zeroCAM is released under a dual-license model.

### Non-Commercial Use

For personal, educational, research, and any other non-commercial purposes, you are free to use, modify, and distribute this software under the terms of the [Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International (CC BY-NC-SA 4.0)](https://creativecommons.org/licenses/by-nc-sa/4.0/) license.

### Commercial Use

If you wish to use this software for any commercial purpose, you must purchase a commercial license. For information **iz1kga (at) gmail.com**.

---

THIS SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.

IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE. USE AT YOUR OWN RISK.
