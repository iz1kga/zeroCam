# Installazione

## Installazione automatica

Sul Raspberry Pi, con un utente che abbia `sudo`:

```bash
wget -O zeroCamInstall https://www.iz1kga.it/zeroCam/zeroCamInstall
sudo bash zeroCamInstall
```

Lo script chiede il tag della versione da installare (per esempio `v1.4.0`) e, alla prima installazione, la password dell'amministratore per l'interfaccia web.

## Che cosa fa lo script

1. **Dipendenze di sistema** — `libcamera`, `python3-picamera2`, `ffmpeg`, `gstreamer`, `jq`, `openssl`, `unzip` e altro tramite `apt`.
2. **Ambiente virtuale** in `/usr/local/zerocam/venv`, creato con `--system-site-packages` per poter usare `picamera2` installato da sistema.
3. **Messa al sicuro dei dati** — se esiste già un'installazione, quanto è rimasto nella cartella dell'applicazione (configurazione, `.env`, log, fotogrammi, immagini) viene spostato nella cartella dei dati.
4. **Rimozione della vecchia applicazione** e download della release richiesta da GitHub.
5. **Configurazione** — la configurazione di default della nuova versione viene fusa con quella esistente: le chiavi nuove entrano, le impostazioni in uso restano.
6. **Memoria condivisa** — un tmpfs da 25 MB montato su `app/shmem`, aggiunto a `/etc/fstab`. Ci passano i fotogrammi condivisi con ONVIF e con l'anteprima web, per non consumare la microSD.
7. **Dipendenze Python** dal `requirements.txt` della release.
8. **Chiavi** — creazione di `.env` con `DEVICE_ID` (UUID) e `ZEROCAM_SECRET_KEY` (32 byte casuali), se non esistono già.
9. **Password** dell'interfaccia web, salvata come hash nella configurazione.
10. **sudoers** — regola che consente il riavvio del sistema dal pulsante dell'interfaccia.
11. **Identità sulla rete** — hostname `zerocam-XXXX` ricavato dal seriale del Raspberry, Avahi attivo e annuncio del servizio web.
12. **Permessi di rete** — regola polkit che consente all'utente del servizio di configurare NetworkManager, e paese del wifi, senza il quale la radio resta bloccata.
13. **Hotspot di appoggio** — nome e password generati e scritti in configurazione, poi mostrati a fine installazione per l'etichetta.
14. **Servizio systemd** `zerocam.service`, abilitato all'avvio e fatto partire.

Prima di ogni altra cosa lo script verifica che il sistema sia Bookworm o successivo: senza `nmcli` si ferma senza installare nulla. Il capitolo *La rete* spiega perché.

## Preparare una webcam da consegnare

Chi costruisce la webcam la installa sul proprio banco, con una rete a disposizione, e poi la spedisce a chi la userà: quello la accende in un posto dove non conosce nessuna rete. Perché sia configurabile senza terminale e senza schermo, quello che serve è tutto nel riquadro stampato a fine installazione:

```
  Da riportare sull'etichetta del dispositivo
  ------------------------------------------
  Indirizzo:            http://zerocam-a1b2.local:8080/
  Rete di appoggio:     zeroCAM-a1b2
  Password della rete:  hw3xpukcty
  Indirizzo da hotspot: http://10.42.0.1:8080/
```

La password dell'hotspot viene mostrata solo lì: dopo si legge dall'interfaccia, in **Configuration → Network**. Va riportata sull'etichetta prima che il dispositivo parta, perché è l'unico modo che l'utente avrà di entrare.

All'accensione, non trovando nessuna rete conosciuta, la webcam accende la propria dopo un paio di minuti. L'utente vi si collega, apre `http://10.42.0.1:8080/`, entra con le credenziali dell'interfaccia e indica il proprio wifi dalla pagina *Network*. Da quel momento la webcam è sulla rete di casa e risponde al primo dei due indirizzi.

Conviene provare la sequenza una volta sul banco, staccando il cavo e verificando che l'hotspot compaia: è l'unica prova che dice se il paese del wifi è stato impostato davvero.

## Dove stanno i file

```
/usr/local/zerocam/app      codice: cancellato e riscritto a ogni aggiornamento
/usr/local/zerocam/data     dati: mai toccati dall'installer
/usr/local/zerocam/venv     ambiente virtuale Python
```

Nella cartella dei dati:

| File o cartella | Contenuto |
|---|---|
| `.conf.json` | Configurazione, con i campi sensibili cifrati |
| `.env` | `DEVICE_ID` e `ZEROCAM_SECRET_KEY` |
| `.privacy_mask.json` | Poligoni delle maschere privacy |
| `.capture_info` | Ultimi indici di esposizione e guadagno riusciti |
| `latest.jpg` | Ultima immagine pubblicata |
| `logs/` | `zerocam.log` (rotazione giornaliera, 7 giorni) e `stats.json` |
| `images/` | Archivio di debug degli scatti, se attivo |
| `timelapse_frames/` | Fotogrammi raccolti per il timelapse |
| `timelapse/` | Video montati, se si sceglie di conservarli |

> **Nota** — chi aggiorna da una versione che teneva tutto dentro `app/` non deve fare nulla: l'installer sposta i file prima di rimuovere la cartella, e al primo avvio l'applicazione ripete il controllo e scrive nel log ciò che ha spostato.

## Variabili d'ambiente

Sono lette dal servizio tramite `EnvironmentFile=/usr/local/zerocam/data/.env`.

| Variabile | Obbligatoria | Significato |
|---|---|---|
| `ZEROCAM_SECRET_KEY` | sì | Chiave da cui deriva la cifratura dei segreti nella configurazione |
| `DEVICE_ID` | sì | Identificativo univoco del dispositivo |
| `ZEROCAM_DATA_DIR` | no | Sposta altrove l'intera cartella dei dati |
| `LOG_LEVEL` | no | `DEBUG`, `INFO` (default), `WARNING`, `ERROR` |

> **Attenzione** — `ZEROCAM_SECRET_KEY` non è recuperabile. Se va persa, le password salvate in configurazione diventano illeggibili e vanno reinserite. Il backup dalla pagina System non dipende da questa chiave: è pensato apposta per sopravvivere a una reinstallazione.

## Gestione del servizio

```bash
sudo systemctl status zerocam.service      # stato
sudo systemctl restart zerocam.service     # riavvio
sudo systemctl stop zerocam.service        # arresto
journalctl -u zerocam.service -f           # log del servizio
tail -f /usr/local/zerocam/data/logs/zerocam.log
```

L'applicazione, quando si arresta in modo controllato, esce con codice diverso da zero: `Restart=on-failure` la fa ripartire da sola. È il meccanismo usato dal pulsante di riavvio dell'interfaccia.

## Aggiornamento

Si rilancia lo stesso script indicando il nuovo tag:

```bash
sudo bash zeroCamInstall
```

Configurazione, chiavi, log, fotogrammi e immagini restano al loro posto. Conviene comunque scaricare un backup della configurazione dalla pagina **System** prima di un aggiornamento importante.

## Disinstallazione

```bash
sudo systemctl disable --now zerocam.service
sudo rm /etc/systemd/system/zerocam.service /etc/sudoers.d/010_zerocam-reboot
sudo systemctl daemon-reload
sudo umount /usr/local/zerocam/app/shmem
# togliere a mano la riga di /etc/fstab relativa a shmem
sudo rm -rf /usr/local/zerocam
```

L'ultimo comando cancella anche i dati: se servono ancora, prima si copia altrove `/usr/local/zerocam/data`.
