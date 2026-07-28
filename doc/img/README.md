# Immagini del manuale

## Diagrammi

Sono generati da sorgente, non disegnati a mano: dopo una modifica al software si aggiorna il `.dot` (o lo script Python) e si rigenera.

```bash
sudo apt install graphviz python3-matplotlib
./genera-diagrammi.sh
```

| Sorgente | Immagine | Usata in |
|---|---|---|
| `architettura.dot` | `architettura.png` | 01 Introduzione |
| `ciclo-scatto.dot` | `ciclo-scatto.png` | 05 Cattura delle immagini |
| `pipeline-streaming.dot` | `pipeline-streaming.png` | 09 Streaming |
| `fasi-giorno.py` | `fasi-giorno.png` | 04 Configurazione di base |

## Schermate

Si rigenerano da qui, senza toccare la webcam:

```bash
pip install flask playwright pillow && playwright install chromium
python3 genera-screenshot.py v1.1.4
cp shots/*.png .
```

Lo script fa girare l'interfaccia vera - gli stessi template, `app.js`, CSS e loghi del repository - contro un backend finto che risponde alle API con dati d'esempio, e la fotografa con Chromium a 1920×961. Ne discendono tre vantaggi: le schermate restano tutte alla stessa versione e allo stesso aspetto, si rifanno in un minuto dopo ogni modifica all'interfaccia, e non contengono un solo dato reale da oscurare.

Le pagine da catturare sono elencate in `PAGES` dentro lo script; i dati d'esempio - configurazione, assets, maschere, statistiche, log - stanno in cima allo stesso file.

Restano acquisite a mano solo le schermate che l'applicazione non può mostrare da sé, come quelle della Google Cloud Console (`gcp-*.png`). Per quelle vale: zoom al **100%**, nessun dato riservato a schermo (Client ID, Client Secret, chiavi di streaming), e un rettangolo pieno - non una sfocatura - su ciò che va coperto.

| File | Cosa inquadrare | Capitolo |
|---|---|---|
| `ui-cam-control.png` | Pagina Cam Control con un'immagine recente e due maschere privacy disegnate | 03, 06 |
| `ui-cam-control-anteprima.png` | Stessa pagina con l'interruttore *Anteprima diretta* attivo e visibile | 09 |
| `ui-config-camera.png` | Configuration → Camera, scheda di una fase notturna, con i campi di luminosità | 05 |
| `ui-config-stream.png` | Configuration → Stream, dalla chiave (oscurata) fino alle destinazioni aggiuntive | 09 |
| `ui-config-annotation.png` | Configuration → Annotation con i campi compilati | 07 |
| `ui-config-timelapse.png` | Configuration → Timelapse | 10 |
| `ui-config-overlays.png` | Configuration → Overlays con i loghi presi dagli assets | 07 |
| `ui-config-assets.png` | Configuration → Assets con audio e loghi caricati | 07 |
| `ui-timelapse-galleria.png` | Pagina Timelapse con galleria e riquadro di stato | 10 |
| `ui-status.png` | Pagina Status con indicatori e grafici popolati | 12 |
| `ui-system-backup.png` | Pagina System: password, porte e certificato, backup | 12 |
| `foto-annotata.png` | Uno scatto pubblicato, con barra di annotazione e logo | 07 |
| `foto-privacy.png` | Uno scatto con una zona sfocata e una coperta, ben riconoscibili | 06 |

Tutte le schermate dell'elenco sono presenti e già inserite nei capitoli indicati. Per aggiungerne altre:

```markdown
![Didascalia che spiega cosa guardare.](img/ui-cam-control.png){ width=95% }
```
