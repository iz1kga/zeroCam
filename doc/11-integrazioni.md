# Integrazioni

## ONVIF

Il servizio ONVIF fa vedere zeroCAM come una telecamera di rete a software di videosorveglianza e NVR, che possono così prelevare istantanee e interrogare il profilo media.

**Configuration → ONVIF**

| Campo | Significato |
|---|---|
| Enabled | Attiva il servizio |
| ONVIF Snapshot Width (px) | Larghezza dell'istantanea; l'altezza segue il rapporto dello streaming |
| Password | Password per l'accesso; l'utente è `onvif` |

Il servizio si innesta sulla stessa porta dell'interfaccia web (8080) e risponde su:

| Percorso | Uso |
|---|---|
| `/onvif/device_service` | Servizio dispositivo (capacità, informazioni, data e ora) |
| `/onvif/media_service` | Servizio media (profili, URI dello stream, URI dell'istantanea) |
| `/snapshot.jpg` | Istantanea corrente in JPEG |

L'istantanea è il fotogramma condiviso prodotto dallo streaming, aggiornato una volta al secondo, con le maschere privacy già applicate. **Ne consegue che le istantanee ONVIF sono disponibili solo mentre lo streaming è attivo**: a streaming fermo il servizio restituisce l'ultimo fotogramma disponibile.

L'accesso a `/snapshot.jpg` è protetto da autenticazione HTTP Basic; l'opzione `allow_unsecure` nella configurazione consente l'accesso senza credenziali, comodo con NVR poco collaborativi ma da usare solo su reti fidate.

Abilitare o disabilitare ONVIF richiede il riavvio dell'applicazione: le rotte vengono registrate all'avvio.

## MQTT

L'integrazione MQTT serve a due cose: ricevere comandi e pubblicare diagnostica. È pensata per chi gestisce più webcam da un sistema centrale.

La configurazione (`mqtt` in `.conf.json`) prevede host, porta, utente, password e un interruttore di abilitazione. La sezione corrispondente dell'interfaccia è al momento nascosta: si configura modificando il file a servizio fermo.

I topic sono costruiti sull'identificativo del dispositivo (`DEVICE_ID` nel file `.env`):

| Topic | Direzione | Contenuto |
|---|---|---|
| `tm_webcams/<DEVICE_ID>/command` | in ingresso | Comandi, in JSON |
| `tm_webcams/<DEVICE_ID>/diagnostic` | in uscita | Stato del dispositivo, in JSON |

### Comandi accettati

```json
{ "action": "capture" }      // scatto immediato
{ "action": "diagnostic" }   // pubblica subito la diagnostica
{ "action": "restart" }      // arresta l'applicazione, che systemd fa ripartire
```

### Diagnostica pubblicata

Viene inviata ogni 60 secondi e a ogni cambio di stato rilevante. Contiene:

* `deviceDetails` — la sezione di configurazione del dispositivo;
* `deviceStatus` — lo stato corrente (`Idle`, `Capturing Image`, `Uploading Image`, `Building timelapse`, `Restarting`…);
* `hardwareStatus` — temperatura, uso di CPU, memoria e disco;
* `dayPeriod` — la fase del giorno in corso;
* `lastCapture` e `lastCapture_dayperiod` — data e fase dell'ultimo scatto;
* `nextCapture` — orario del prossimo scatto pianificato.

Un sistema di monitoraggio può quindi accorgersi che una webcam non scatta da troppo tempo, o che la temperatura della CPU sta salendo, senza interrogare il dispositivo.
