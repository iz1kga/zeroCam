#!/usr/bin/env python3
"""
Compone la copertina del manuale: fascia scura con il titolo, una foto
della webcam e il piede con versione e data.

La foto e i testi cambiano a ogni release, quindi l'immagine non viene
versionata: la rigenera build.sh a ogni compilazione.

    ./genera-copertina.py --versione v1.2.0 --data 26/07/2026
"""

import argparse
import os

from PIL import Image, ImageDraw, ImageFont

QUI = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.path.join(QUI, "..", "..", "static", "css", "fonts")

# A4 a 150 dpi: abbastanza per la stampa, senza gonfiare il PDF.
LARGHEZZA, ALTEZZA = 1240, 1754
FASCIA_TITOLO = 620          # altezza della fascia scura in alto
FASCIA_FOTO = 700            # altezza della banda con la fotografia

SCURO = (28, 39, 51)
SCURO_CHIARO = (51, 68, 92)
ACCENTO = (200, 120, 48)
CHIARO = (247, 247, 245)
TESTO = (40, 48, 58)


def font(nome, dimensione):
    """Il carattere dell'applicazione, con ripiego su quelli di sistema."""
    candidati = [
        os.path.join(FONT_DIR, nome),
        f"/usr/share/fonts/truetype/dejavu/{nome}",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for percorso in candidati:
        if os.path.exists(percorso):
            return ImageFont.truetype(percorso, dimensione)
    return ImageFont.load_default()


def sfumatura(disegno, altezza):
    """Fascia scura con una leggera sfumatura verticale."""
    for y in range(altezza):
        k = y / max(1, altezza - 1)
        colore = tuple(round(a + (b - a) * k) for a, b in zip(SCURO, SCURO_CHIARO))
        disegno.line([(0, y), (LARGHEZZA, y)], fill=colore)


def banda_foto(copertina, percorso):
    """Inserisce la fotografia ritagliata al centro della banda."""
    if not os.path.exists(percorso):
        return
    with Image.open(percorso) as foto:
        foto = foto.convert("RGB")
        scala = max(LARGHEZZA / foto.width, FASCIA_FOTO / foto.height)
        nuova = (round(foto.width * scala), round(foto.height * scala))
        foto = foto.resize(nuova, Image.LANCZOS)
        sinistra = (foto.width - LARGHEZZA) // 2
        alto = (foto.height - FASCIA_FOTO) // 2
        foto = foto.crop((sinistra, alto, sinistra + LARGHEZZA, alto + FASCIA_FOTO))
        copertina.paste(foto, (0, FASCIA_TITOLO))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--versione", default="")
    parser.add_argument("--data", default="")
    parser.add_argument("--foto", default=os.path.join(QUI, "foto-annotata.png"))
    parser.add_argument("--out", default=os.path.join(QUI, "copertina.png"))
    args = parser.parse_args()

    copertina = Image.new("RGB", (LARGHEZZA, ALTEZZA), CHIARO)
    disegno = ImageDraw.Draw(copertina)

    sfumatura(disegno, FASCIA_TITOLO)
    banda_foto(copertina, args.foto)

    # Titolo e sottotitolo nella fascia scura
    disegno.text((90, 250), "zeroCAM", font=font("Arial.ttf", 128), fill=CHIARO)
    disegno.line([(92, 410), (300, 410)], fill=ACCENTO, width=6)
    disegno.text((90, 445), "Manuale d'uso e di configurazione",
                 font=font("Arial.ttf", 44), fill=(214, 220, 228))

    # Filetto di stacco fra foto e piede
    y_piede = FASCIA_TITOLO + FASCIA_FOTO
    disegno.rectangle([(0, y_piede), (LARGHEZZA, y_piede + 8)], fill=ACCENTO)

    # Piede: a cosa serve, poi autore a sinistra e versione a destra
    disegno.text((90, y_piede + 60),
                 "Webcam paesaggistica per Raspberry Pi 5\ne Raspberry Pi Camera Module HQ",
                 font=font("Arial.ttf", 40), fill=TESTO, spacing=16)

    disegno.line([(90, ALTEZZA - 224), (LARGHEZZA - 90, ALTEZZA - 224)],
                 fill=(206, 210, 214), width=2)

    disegno.text((90, ALTEZZA - 194), "IZ1KGA — www.iz1kga.it",
                 font=font("Arial.ttf", 34), fill=TESTO)
    disegno.text((90, ALTEZZA - 138),
                 "Licenza CC BY-NC-SA 4.0 per uso non commerciale",
                 font=font("Arial.ttf", 26), fill=(120, 128, 138))

    if args.versione:
        disegno.text((LARGHEZZA - 90, ALTEZZA - 194), f"Versione {args.versione}",
                     font=font("Arial.ttf", 34), fill=SCURO_CHIARO, anchor="ra")
    if args.data:
        disegno.text((LARGHEZZA - 90, ALTEZZA - 138), args.data,
                     font=font("Arial.ttf", 26), fill=(120, 128, 138), anchor="ra")

    copertina.save(args.out)
    print(f"Creato {args.out}")


if __name__ == "__main__":
    main()
