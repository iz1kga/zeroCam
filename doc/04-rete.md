# La rete

## Che cosa serve

La rete la gestisce **NetworkManager**, che è quello che Raspberry Pi OS installa e usa da Bookworm in avanti. Le versioni precedenti configuravano la rete con `dhcpcd` e `wpa_supplicant`, che sono un'altra cosa e non parlano la stessa lingua: su un sistema del genere la pagina *Network* dichiara che NetworkManager non risponde e non offre alcun comando, e la rete va configurata a mano dal terminale.

Non è una svista da colmare più avanti. zeroCAM richiede Raspberry Pi OS a 64 bit basato su Bookworm o successivo, e su quello soltanto è provato.

Per verificare cosa sta girando:

```bash
nmcli general status
```

Se il comando non esiste, il sistema è troppo vecchio.

## La pagina Network

Elenca le interfacce che NetworkManager conosce — tipicamente `eth0` ed `wlan0` — con lo stato, il profilo attivo, gli indirizzi, il gateway e i DNS. In alto un'etichetta riassume la connettività secondo NetworkManager:

| Etichetta | Significato |
|---|---|
| Internet raggiungibile | La webcam esce davvero: upload, diretta e timelapse possono funzionare |
| Rete senza internet | C'è un indirizzo, ma non si arriva fuori |
| Dietro un portale di accesso | La rete richiede un accesso da browser, che la webcam non può fare |
| Nessuna connettività | Nessuna interfaccia utilizzabile |

È una distinzione che vale la pena guardare prima di cercare altrove: un dispositivo con un indirizzo valido e nessuna uscita verso internet ha tutti i sintomi di un problema di upload, ma la causa sta qui.

La pagina si aggiorna da sola ogni dieci secondi, perché lo stato cambia anche senza toccare nulla — un cavo staccato, un access point che sparisce.

## Indirizzo automatico o fisso

Il pulsante **Indirizzo** accanto a un'interfaccia apre la scelta fra *Automatico (DHCP)* e *Indirizzo fisso*. Vale per la cablata e per il wifi allo stesso modo: cambia solo il profilo su cui si scrive.

Con l'indirizzo fisso servono:

* **Indirizzo e prefisso**, nella forma `192.168.1.50/24`. Il prefisso non è facoltativo: senza, l'indirizzo verrebbe interpretato come `/32` e il dispositivo resterebbe isolato dalla sua stessa rete.
* **Gateway**, che deve appartenere alla rete appena indicata. Un gateway fuori dalla sottorete è irraggiungibile per definizione.
* **DNS**, uno per riga. Senza, restano solo quelli eventualmente forniti da un'altra interfaccia.

I valori sono controllati prima di toccare qualsiasi cosa, e un dato malformato viene rifiutato subito. Il motivo è pratico: a metà riconfigurazione l'interfaccia è già giù, e un errore scoperto in quel momento lascerebbe il dispositivo irraggiungibile proprio quando servirebbe rimediare.

Tornando all'automatico, indirizzo, gateway e DNS manuali vengono cancellati e non solo ignorati. Restassero lì, i DNS si sommerebbero a quelli del DHCP e l'indirizzo tornerebbe in uso al primo ritorno all'indirizzo fisso.

**Una avvertenza che conviene leggere prima di premere Applica.** Se si sta navigando proprio dall'interfaccia che si sta riconfigurando, l'indirizzo cambia sotto la connessione aperta e la risposta non arriverà mai: la pagina resta in attesa e dopo venticinque secondi lo dice. Non è un errore, è l'esito normale. Si riapre l'interfaccia al nuovo indirizzo, e l'esito vero resta scritto nel log.

## Collegare il wifi

**Cerca reti** elenca quelle in portata, la più forte per prima. La scansione occupa la radio per qualche secondo, quindi non viene fatta a ogni aggiornamento della pagina ma solo quando la si chiede.

Delle reti con lo stesso nome viste da più access point ne compare una sola, quella col segnale migliore: a chi configura interessa scegliere una rete, non un ripetitore.

Scelta la rete, si scrive la password — da 8 a 63 caratteri, come vuole WPA — e si preme *Connetti*. La risposta arriva a tentativo concluso e può metterci fino a un minuto: è l'unico modo per riportare il motivo di un rifiuto invece di lasciarlo indovinare. Le reti aperte non chiedono nulla e sono marcate come tali.

**Il wifi si può usare anche con il cavo collegato.** Le due interfacce restano attive insieme; per il traffico in uscita NetworkManager preferisce la cablata, che ha una metrica più bassa, e passa al wifi se il cavo cade. È il modo più comodo per preparare il wifi con calma prima di spostare la webcam dove il cavo non arriva.

### Reti nascoste

Una rete che non annuncia il proprio nome non compare in nessuna scansione, quindi non si può scegliere da un elenco. Sotto la lista, la voce **Rete nascosta** apre i campi per scriverne nome e password a mano.

## Reti memorizzate

Ogni rete a cui la webcam si è collegata resta salvata in NetworkManager, che ci si ricollega da solo quando la trova. L'elenco in fondo alla pagina le mostra, segnalando quale è attiva e su quale interfaccia.

**Dimentica** cancella il profilo, password compresa. Serve quando una rete non esiste più, o quando la sua password è cambiata: senza cancellarlo, il vecchio profilo continuerebbe a essere ritentato.

Anche un tentativo fallito non lascia nulla dietro di sé. Il profilo appena creato viene rimosso, altrimenti NetworkManager continuerebbe per conto suo a riprovare con la password sbagliata.

## Che cosa non finisce nel backup

Le reti e le loro password stanno in NetworkManager, non in `.conf.json`: il backup della configurazione (**System → Backup**) non se le porta dietro, e un ripristino non le tocca. È voluto. Un backup ripristinato su un altro dispositivo, magari in un altro luogo, non ha motivo di portarsi appresso le reti di casa di qualcun altro, e NetworkManager le sue le conserva già per conto proprio.

Di conseguenza, dopo una reinstallazione o un cambio di SD la rete va riconfigurata: è l'unica cosa che il ripristino non rimette a posto.

## Le API

| Percorso | Metodo | Effetto |
|---|---|---|
| `/api/network` | GET | Interfacce, indirizzi, connettività, reti salvate |
| `/api/network/scan` | GET | Reti wifi in portata |
| `/api/network/wifi` | POST | Collega a una rete (`ssid`, `password`, `hidden`) |
| `/api/network/forget` | POST | Cancella un profilo salvato (`name`) |
| `/api/network/address` | POST | Indirizzo automatico o fisso (`connection`, `method`, `address`, `gateway`, `dns`) |

Come tutte le altre rotte dell'interfaccia, richiedono una sessione autenticata.

## Dal terminale

Quando l'interfaccia web non è raggiungibile — che è poi il caso in cui la rete non funziona — le stesse cose si fanno con `nmcli`, che è quello che l'applicazione usa sotto:

```bash
nmcli device status                    # interfacce e profili attivi
nmcli device wifi list --rescan yes    # reti in portata
nmcli device wifi connect "CasaMia" password "..."
nmcli connection show                  # profili salvati
nmcli connection modify "Wired connection 1" \
      ipv4.method manual ipv4.addresses 192.168.1.50/24 \
      ipv4.gateway 192.168.1.1 ipv4.dns "8.8.8.8 1.1.1.1"
nmcli connection up "Wired connection 1"
```
