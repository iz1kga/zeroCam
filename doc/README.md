# Manuale zeroCAM

Il manuale è scritto in Markdown, un file per capitolo, e viene unito in un unico PDF (o HTML) da `build.sh`.

## Capitoli

| File | Capitolo |
|---|---|
| [01-introduzione.md](01-introduzione.md) | Che cos'è zeroCAM, requisiti, architettura |
| [02-installazione.md](02-installazione.md) | Installazione, cartelle, servizio, aggiornamento |
| [03-interfaccia-web.md](03-interfaccia-web.md) | Le pagine dell'interfaccia e le API |
| [04-configurazione-base.md](04-configurazione-base.md) | Device Details, fasi del giorno, sicurezza |
| [05-cattura-immagini.md](05-cattura-immagini.md) | Ciclo di scatto, esposizione, ritaglio, focus aid |
| [06-privacy-mask.md](06-privacy-mask.md) | Maschere privacy su foto e video |
| [07-annotazione-loghi.md](07-annotazione-loghi.md) | Barra di annotazione e loghi |
| [08-pubblicazione-immagini.md](08-pubblicazione-immagini.md) | Upload FTP e HTTP |
| [09-streaming.md](09-streaming.md) | Diretta YouTube, ritrasmissione, anteprima |
| [10-timelapse.md](10-timelapse.md) | Raccolta, montaggio, pubblicazione, galleria |
| [11-onvif.md](11-onvif.md) | Integrazione ONVIF |
| [12-manutenzione.md](12-manutenzione.md) | Backup, log, statistiche, spazio su disco |
| [13-risoluzione-problemi.md](13-risoluzione-problemi.md) | Sintomi, cause, rimedi |
| [14-riferimento-configurazione.md](14-riferimento-configurazione.md) | Tutte le chiavi di `.conf.json` |
| [15-licenza.md](15-licenza.md) | Termini di licenza |

L'ordine dei capitoli nel PDF è quello alfabetico dei nomi dei file: per inserirne uno nuovo basta numerarlo di conseguenza.

In [bozze/](bozze/) stanno i capitoli non ancora pronti: `build.sh` non li raccoglie, perché nel manuale entra solo ciò che è completo e funzionante. Un capitolo esce dalla bozza spostandolo in questa cartella con il suo numero.

## Immagini

Stanno in [img/](img/). I diagrammi si rigenerano da sorgente con `img/genera-diagrammi.sh` (serve `graphviz` e `matplotlib`) e vanno aggiornati quando cambia ciò che descrivono. Le schermate dell'interfaccia e le foto della webcam vanno acquisite dal dispositivo in funzione: l'elenco di quelle attese, con nomi e regole, è in [img/README.md](img/README.md).

## Costruire il PDF

```bash
sudo apt install pandoc texlive-xetex texlive-fonts-recommended lmodern
./build.sh
```

Produce `zeroCAM-manuale.pdf` con copertina, indice e capitoli numerati.

La copertina è composta da `img/genera-copertina.py` (fascia con il titolo, una foto della webcam, piede con autore, versione e data) e viene rifatta a ogni compilazione, perché versione e data cambiano; `copertina.tex` la sostituisce al frontespizio di pandoc. Per cambiare la fotografia basta `--foto`:

```bash
python3 img/genera-copertina.py --foto img/foto-privacy.png --versione v1.2.0 --data 01/09/2026
```

La versione è presa dal file `VERSION` del progetto, o dal tag git se si lavora sul repository.

Senza LaTeX si può ottenere una pagina HTML autonoma, con tutto incorporato:

```bash
./build.sh html
```

## Convenzioni di scrittura

* Un file per capitolo, che inizia con un titolo di primo livello (`#`); le sezioni interne partono da `##`.
* Le impostazioni dell'interfaccia si citano come **Configuration → Stream**, i percorsi come `/usr/local/zerocam/data`.
* Le tabelle usano la sintassi a pipe, supportata da pandoc senza estensioni particolari.
* I file prodotti (`zeroCAM-manuale.pdf`, `.html`) non vengono versionati.
