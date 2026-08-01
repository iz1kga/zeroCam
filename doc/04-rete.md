# La rete

## Che cosa serve

La rete la gestisce **NetworkManager**, che è quello che Raspberry Pi OS installa e usa da Bookworm in avanti. Le versioni precedenti configuravano la rete con `dhcpcd` e `wpa_supplicant`, che sono un'altra cosa e non parlano la stessa lingua: su un sistema del genere la pagina *Network* dichiara che NetworkManager non risponde e non offre alcun comando, e la rete va configurata a mano dal terminale.

Non è una svista da colmare più avanti. zeroCAM richiede Raspberry Pi OS a 64 bit basato su Bookworm o successivo, e su quello soltanto è provato.

Per verificare cosa sta girando:

```bash
nmcli general status
```

Se il comando non esiste, il sistema è troppo vecchio. L'installatore fa lo stesso controllo e si ferma prima di installare qualsiasi cosa.

### I permessi

Il servizio gira come utente normale, non come root, e senza un'autorizzazione esplicita ogni comando di scrittura verrebbe rifiutato: la pagina *Network* mostrerebbe lo stato ma non potrebbe cambiare nulla. L'installazione crea per questo una regola polkit in `/etc/polkit-1/rules.d/10-zerocam-network.rules`, che concede a quell'utente — e solo a lui — le azioni di NetworkManager.

Il numero iniziale non è arbitrario. polkit valuta i file in ordine alfabetico e si ferma al primo che risponde, e Raspberry Pi OS installa `49-polkit-pkla-compat.rules`, il ponte verso i vecchi file `.pkla`, che risponde e interrompe la catena. Una regola numerata `50-` non verrebbe mai eseguita, e il sintomo è particolarmente ostico: il file risulta caricato, nel log di polkit non compare nessun errore, e ogni modifica fallisce con `Insufficient privileges`.

Su un'installazione aggiornata da una versione precedente la regola viene creata al primo aggiornamento. Se la pagina legge ma ogni modifica fallisce, è il primo posto da guardare.

### Il paese del wifi

La radio resta bloccata finché non è dichiarato il paese: `rfkill list` mostra `Soft blocked: yes` e nessun hotspot può partire. L'installazione lo chiede, proponendo `IT`. Si cambia in seguito con:

```bash
sudo raspi-config nonint do_wifi_country IT
```

## Il nome del dispositivo

L'installazione dà alla webcam un hostname unico, `zerocam-XXXX`, dove le quattro cifre finali vengono dal seriale del Raspberry. Grazie ad Avahi, che Raspberry Pi OS installa di suo, il dispositivo risponde a quel nome sulla rete locale:

```
http://zerocam-a1b2.local:8080/
```

Non serve conoscerne l'indirizzo IP, che con il DHCP può cambiare.

Il suffisso dal seriale non è un vezzo. Due webcam con lo stesso nome creano un conflitto che Avahi risolve da sé rinominando la seconda in `zerocam-2.local`, ma quale sia la seconda dipende dall'ordine di accensione e può cambiare a ogni riavvio: un'etichetta stampata non varrebbe più nulla. Con il suffisso il conflitto non si presenta.

Lo stesso suffisso compone il nome dell'hotspot di appoggio, `zeroCAM-XXXX`, così l'etichetta, la rete a cui collegarsi e l'indirizzo da digitare dicono tutti la stessa cosa.

Se al momento dell'installazione l'hostname era già stato cambiato a mano, viene lasciato com'è: è una scelta di chi ha preparato il dispositivo.

### Il nome leggibile

Accanto all'hostname, la webcam annuncia il proprio servizio web con il nome di **Configuration → Device Details**. È quello che compare nei browser Bonjour e nella sezione *Rete* dei gestori di file: si legge "Villar Focchiardo" invece di `zerocam-a1b2`, che come nome è corretto ma non dice niente.

L'annuncio è un file in `/etc/avahi/services/`, riscritto dall'applicazione quando il nome cambia; Avahi lo rilegge da sé. Spegnendo l'HTTP l'annuncio sparisce, perché prometterebbe una porta che non risponde.

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

## L'hotspot di appoggio

Una webcam consegnata già installata viene accesa dove sarà usata, e lì non conosce nessuna rete. Perché sia configurabile senza terminale e senza schermo, quando resta senza connettività accende un access point proprio: ci si collega dal telefono e l'interfaccia risponde su `http://10.42.0.1:8080`, da dove si indica il wifi di casa.

Nome della rete e password sono quelli stampati sull'etichetta del dispositivo. Il nome, se non lo si impone, viene ricavato dall'hostname — che l'installazione rende unico per dispositivo — così due webcam accese vicine non si confondono e l'etichetta, l'SSID e l'indirizzo da digitare dicono la stessa cosa. Si cambiano in **Configuration → Network**, ricordando che a quel punto l'etichetta non vale più.

**Senza password l'hotspot non parte.** Un access point aperto darebbe a chiunque passi l'accesso a questa console, che riconfigura e riavvia il dispositivo. La pagina *Network* lo segnala in rosso finché la password manca.

### Quando si accende e quando si spegne

| Situazione | Cosa succede |
|---|---|
| Connettività presente (cavo o wifi) | L'hotspot resta spento |
| Connettività assente da due minuti | L'hotspot si accende |
| Il cavo torna mentre l'hotspot è acceso | L'hotspot si spegne |
| Hotspot acceso, ci sono reti salvate | Ogni dieci minuti la radio viene liberata per poco più di un minuto |

L'attesa di due minuti serve a non far comparire l'access point per un router che si riavvia. Si cambia in **Configuration → Network**.

La finestra di ritentativo esiste perché la radio è una sola: finché l'hotspot è acceso, NetworkManager non può cercare le reti conosciute né riassociarsi. Senza quella pausa periodica, una webcam finita in hotspot ci resterebbe fino al riavvio anche con il suo wifi di nuovo disponibile.

La pausa però stacca chi si è collegato all'hotspot proprio per configurarlo, quindi non si apre mai mentre la pagina *Network* è in uso: le richieste segnalano l'attività, e il watchdog aspetta cinque minuti di quiete. E non si apre affatto se non c'è nessuna rete salvata a cui tornare, perché non servirebbe a niente se non a scollegare chi sta configurando.

### Sbagliare la password non blocca fuori

Collegandosi a una rete l'hotspot si spegne, e con esso la connessione di chi sta configurando proprio da lì: la pagina smette di rispondere ed è normale. Se la password era giusta, la webcam è sulla rete scelta. Se era sbagliata, la connessione fallisce e l'hotspot viene rimesso su subito, in modo che la rete ricompaia e si possa riprovare.

Le protezioni sono due, e volutamente ridondanti. La prima è immediata e sta nella richiesta stessa; se anche quella fallisce, il watchdog se ne accorge al giro successivo e riaccende comunque l'hotspot. In pratica, nel peggiore dei casi la rete torna entro un paio di minuti.

Anche il profilo del tentativo fallito viene cancellato, altrimenti NetworkManager continuerebbe per conto suo a riprovare con la password sbagliata.

### Perché l'applicazione non aspetta più la rete all'avvio

Fino alla versione precedente l'avvio si fermava finché non c'era Internet, riprovando ogni minuto. Con l'hotspot quel comportamento diventava un vicolo cieco: la webcam senza rete non arrivava mai ad avviare l'interfaccia web, quindi nemmeno l'hotspot, e restava configurabile solo da terminale — cioè esattamente ciò che l'hotspot esiste per evitare. Ora la connessione viene guardata e annotata nel log, ma non attesa.

## Che cosa non finisce nel backup

Le reti e le loro password stanno in NetworkManager, non in `.conf.json`: il backup della configurazione (**System → Backup**) non se le porta dietro, e un ripristino non le tocca. Le impostazioni dell'hotspot invece sì, perché sono configurazione e non stato della rete: nome, password e attesa vivono nella sezione `network` di `.conf.json` e seguono il backup come tutto il resto. È voluto. Un backup ripristinato su un altro dispositivo, magari in un altro luogo, non ha motivo di portarsi appresso le reti di casa di qualcun altro, e NetworkManager le sue le conserva già per conto proprio.

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
