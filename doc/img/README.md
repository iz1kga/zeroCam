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

## Schermate da acquisire

Vanno prese dal dispositivo in funzione, che è l'unico posto dove l'interfaccia mostra dati veri. Regole comuni:

* browser a **1400 px** di larghezza, zoom al 100%, finestra senza barre di sviluppo;
* ritagliare solo l'area utile (non serve la barra del browser), formato **PNG**;
* nessun dato riservato a schermo: chiave di streaming, token, Client Secret e Refresh Token vanno oscurati o svuotati prima dello scatto;
* nome del file esattamente come in tabella, in questa cartella.

| File | Cosa inquadrare | Capitolo |
|---|---|---|
| `ui-cam-control.png` | Pagina Cam Control con un'immagine recente e due maschere privacy disegnate | 03, 06 |
| `ui-cam-control-anteprima.png` | Stessa pagina con l'interruttore *Anteprima diretta* attivo e visibile | 09 |
| `ui-config-camera.png` | Configuration → Camera, scheda di una fase notturna, con i campi di luminosità | 05 |
| `ui-config-stream.png` | Configuration → Stream, dalla chiave (oscurata) fino alle destinazioni aggiuntive | 09 |
| `ui-config-annotation.png` | Configuration → Annotation con i campi compilati | 07 |
| `ui-config-timelapse.png` | Configuration → Timelapse | 10 |
| `ui-timelapse-galleria.png` | Pagina Timelapse con galleria e riquadro di stato | 10 |
| `ui-status.png` | Pagina Status con indicatori e grafici popolati | 12 |
| `ui-system-backup.png` | Pagina System, sezione backup e ripristino | 12 |
| `foto-annotata.png` | Uno scatto pubblicato, con barra di annotazione e logo | 07 |
| `foto-privacy.png` | Uno scatto con una zona sfocata e una coperta, ben riconoscibili | 06 |

Una volta messi i file qui, le figure vanno inserite nei capitoli con:

```markdown
![Didascalia che spiega cosa guardare.](img/ui-cam-control.png){ width=95% }
```
