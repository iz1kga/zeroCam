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
    wget https://www.iz1kga.it/zeroCam/zeroCamInstall && sudo bash zeroCamInstall
    ```
2.  Segui le istruzioni a schermo. Ti verrà chiesto di inserire la versione di zeroCAM da installare e di impostare una password per l'amministratore.

### Primo Accesso

Una volta completata l'installazione, puoi accedere all'interfaccia web del dispositivo:

* **URL:** `http://<IP_DEL_TUO_RASPBERRY>:8080/`
* **Username:** `admin`
* **Password:** Quella che hai fornito durante l'installazione.

Ora puoi configurare la tua telecamera e iniziare a usarla!

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
    wget https://www.iz1kga.it/zeroCam/zeroCamInstall && sudo bash zeroCamInstall
    ```
2.  Follow the on-screen instructions. You will be asked to enter the zeroCAM version to install and to set an administrator password.

### First Access

Once the installation is complete, you can access the device's web interface:

* **URL:** `http://<YOUR_RASPBERRY_IP>:8080/`
* **Username:** `admin`
* **Password:** The one you provided during installation.

Now you can configure your camera and start using it!

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
