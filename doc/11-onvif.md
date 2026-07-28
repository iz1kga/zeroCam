# ONVIF

Il servizio ONVIF fa vedere zeroCAM come una telecamera di rete a software di videosorveglianza e NVR, che possono così prelevare istantanee e interrogare il profilo media.

## Configurazione

**Configuration → ONVIF**

| Campo | Significato |
|---|---|
| Enabled | Attiva il servizio |
| ONVIF Snapshot Width (px) | Larghezza dell'istantanea; l'altezza segue il rapporto dello streaming |
| Password | Password per l'accesso; l'utente è `onvif` |

Il servizio si innesta sulla stessa porta HTTP dell'interfaccia web (8080) e risponde su:

| Percorso | Uso |
|---|---|
| `/onvif/device_service` | Servizio dispositivo (capacità, informazioni, data e ora) |
| `/onvif/media_service` | Servizio media (profili, URI dello stream, URI dell'istantanea) |
| `/snapshot.jpg` | Istantanea corrente in JPEG |

ONVIF non parla TLS: se in **System** si spegne l'ascolto in chiaro per lasciare solo l'HTTPS, il servizio resta registrato ma nessun client riesce più a raggiungerlo.

Gli indirizzi che il servizio dichiara nelle risposte — quello del servizio media, dell'istantanea, dello stream — sono costruiti sull'indirizzo con cui il client ha raggiunto la webcam, non su quello che il Raspberry si rileva da solo. Così funzionano anche da una VPN, da un'altra sottorete o attraverso un nome pubblico, dove l'indirizzo locale non sarebbe instradabile.

L'istantanea è il fotogramma condiviso prodotto dallo streaming, aggiornato una volta al secondo, con le maschere privacy già applicate. **Ne consegue che le istantanee ONVIF sono disponibili solo mentre lo streaming è attivo**: a streaming fermo il servizio restituisce l'ultimo fotogramma disponibile.

L'accesso a `/snapshot.jpg` è protetto da autenticazione HTTP Basic; l'opzione `allow_unsecure` nella configurazione consente l'accesso senza credenziali, comodo con NVR poco collaborativi ma da usare solo su reti fidate.

Abilitare o disabilitare ONVIF richiede il riavvio dell'applicazione: le rotte vengono registrate all'avvio.
