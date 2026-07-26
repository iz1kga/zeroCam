# ONVIF

Il servizio ONVIF fa vedere zeroCAM come una telecamera di rete a software di videosorveglianza e NVR, che possono così prelevare istantanee e interrogare il profilo media.

## Configurazione

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
