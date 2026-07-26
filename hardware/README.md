# Hardware: materiale e custodia

Questa cartella raccoglie tutto ciò che serve a procurarsi il materiale e a costruire la custodia di zeroCAM: distinta base, disegni CAD, file pronti per la stampa 3D e istruzioni di montaggio.

> **Licenza** — il materiale meccanico è rilasciato sotto [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/), come il software per l'uso non commerciale. I file nativi sono stati prodotti con **SOLIDWORKS for Makers**, licenza che consente il solo uso non commerciale: chi intende impiegarli in un prodotto commerciale deve procurarsi una licenza adeguata e concordare l'uso con l'autore.

## Come è organizzata

```
hardware/
├── cad/      sorgenti SOLIDWORKS (.sldprt, .sldasm) — Git LFS
├── step/     esportazioni STEP, apribili con qualunque CAD — Git LFS
├── print/    file pronti per la stampa (.3mf, .stl)
├── img/      fotografie del montaggio e rendering
├── README.md questo file: distinta base, stampa, montaggio
└── CHANGELOG.md  storia delle revisioni della meccanica
```

I sorgenti CAD e le esportazioni STEP passano da **Git LFS**: sono binari pesanti e senza LFS ogni revisione resterebbe per intero nella storia del repository. Prima del primo `clone` o `pull` di questa cartella:

```bash
sudo apt install git-lfs     # oppure brew install git-lfs
git lfs install
git lfs pull
```

I file `.3mf` e `.stl` restano fuori da LFS: sono più leggeri e GitHub li mostra direttamente nel browser con un visualizzatore 3D.

Le revisioni non si marcano nel nome dei file — che resta stabile — ma con i tag git e con il `CHANGELOG.md`: con i binari il messaggio di commit è l'unica differenza leggibile.

## Distinta base

> Da compilare. Prezzi indicativi, IVA inclusa, aggiornati alla data indicata in fondo.

### Elettronica

| Qty | Componente | Specifica | Fornitore | Prezzo |
|---:|---|---|---|---:|
| 1 | Raspberry Pi 5 | 4 o 8 GB | | |
| 1 | Raspberry Pi Camera Module HQ | sensore IMX477, attacco C/CS | | |
| 1 | Obiettivo | | | |
| 1 | Alimentatore ufficiale | 27 W USB-C | | |
| 1 | microSD o SSD USB | | | |
| 1 | Cavo FFC per camera | lunghezza: | | |
| | Dissipazione | | | |

### Meccanica e minuteria

| Qty | Componente | Specifica | Fornitore | Prezzo |
|---:|---|---|---|---:|
| | Viti | | | |
| | Inserti filettati | | | |
| | Guarnizione | | | |
| | Pressacavo | | | |
| | Vetro o finestra ottica | | | |
| | Staffa di montaggio | | | |

### Materiale di stampa

| Qty | Materiale | Note |
|---:|---|---|
| | | |

**Totale indicativo:** — · **Prezzi rilevati il:** —

## Stampa 3D

| Parametro | Valore |
|---|---|
| Materiale | |
| Altezza layer | |
| Pareti / perimetri | |
| Riempimento | |
| Supporti | |
| Orientamento consigliato | |
| Tolleranze previste | |

Note su ritiro, resistenza ai raggi UV e alle escursioni termiche: la custodia sta all'aperto tutto l'anno, e la scelta del materiale conta più dei parametri di stampa.

## Montaggio

> Da scrivere, passo per passo, con le fotografie in `img/`.

1.
2.
3.

## Manutenzione della custodia

Note su pulizia del vetro, controllo delle guarnizioni, condensa e ventilazione.
