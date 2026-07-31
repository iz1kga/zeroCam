#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Etichetta del dispositivo, con i codici QR per l'utente finale.

Chi riceve la webcam la accende dove non conosce nessuna rete: l'unico
modo per entrarci è l'hotspot di appoggio, e l'unica cosa che ce lo dice è
quello che sta scritto sulla scatola. Questo script produce quel foglietto.

Due QR, perché uno solo non può fare entrambe le cose. Il primo porta le
credenziali della rete di appoggio nel formato che telefoni Android e iOS
riconoscono dalla fotocamera, quindi il collegamento è un tocco. Il
secondo è l'indirizzo dell'interfaccia una volta collegati, che altrimenti
andrebbe digitato a memoria.

Viene richiamato dall'installatore, che gli passa quello che ha appena
deciso. Si può rilanciare a mano per ristampare un'etichetta persa:

    /usr/local/zerocam/venv/bin/python genera_etichetta.py \\
        --hostname zerocam-a1b2 --ssid zeroCAM-a1b2 --password hw3xpukcty \\
        --output /tmp/etichetta.png
"""

import argparse
import os
import sys

import qrcode
from PIL import Image, ImageDraw, ImageFont

# 60x100 mm a 300 dpi: entra in una tasca portaetichette da magazzino e
# resta leggibile stampata in bianco e nero.
WIDTH, HEIGHT = 709, 1181
MARGIN = 40

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]


def wifi_payload(ssid, password, hidden=False):
    """
    La stringa che i telefoni leggono come "collegati a questa rete".

    Il formato vuole che punto e virgola, due punti, virgole, virgolette e
    barre rovesce siano protetti: un SSID che ne contiene uno spezzerebbe
    il campo e il telefono leggerebbe una rete che non esiste.
    """
    def protect(value):
        for char in ("\\", ";", ",", ":", '"'):
            value = value.replace(char, "\\" + char)
        return value

    return (f"WIFI:S:{protect(ssid)};T:WPA;P:{protect(password)};"
            f"{'H:true;' if hidden else ''};")


def _font(size, bold=False):
    for path in (reversed(FONT_CANDIDATES) if bold else FONT_CANDIDATES):
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                pass
    # Senza font di sistema l'etichetta esce comunque, solo bruttina: non
    # è un motivo per non produrla.
    return ImageFont.load_default()


def _qr(data, size):
    code = qrcode.QRCode(box_size=10, border=2,
                         error_correction=qrcode.constants.ERROR_CORRECT_M)
    code.add_data(data)
    code.make(fit=True)
    image = code.make_image(fill_color="black", back_color="white").convert("RGB")
    return image.resize((size, size), Image.NEAREST)


def _centered(draw, y, text, font, fill=(0, 0, 0)):
    box = draw.textbbox((0, 0), text, font=font)
    draw.text(((WIDTH - (box[2] - box[0])) / 2, y), text, font=font, fill=fill)
    return y + (box[3] - box[1])


def build(hostname, ssid, password, port=8080, hotspot_url="http://10.42.0.1:8080/"):
    image = Image.new("RGB", (WIDTH, HEIGHT), "white")
    draw = ImageDraw.Draw(image)

    titolo = _font(46, bold=True)
    testo = _font(30)
    piccolo = _font(24)
    mono = _font(32, bold=True)

    y = MARGIN
    y = _centered(draw, y, "zeroCAM", titolo) + 30
    y = _centered(draw, y, f"http://{hostname}.local:{port}/", testo) + 40

    draw.line([(MARGIN, y), (WIDTH - MARGIN, y)], fill=(180, 180, 180), width=2)
    y += 30

    y = _centered(draw, y, "1. Collegati a questa rete", testo) + 16
    qr_size = 300
    image.paste(_qr(wifi_payload(ssid, password), qr_size),
                (int((WIDTH - qr_size) / 2), y))
    y += qr_size + 16
    y = _centered(draw, y, ssid, mono) + 10
    y = _centered(draw, y, password, mono) + 36

    y = _centered(draw, y, "2. Apri questo indirizzo", testo) + 16
    qr_size = 250
    image.paste(_qr(hotspot_url, qr_size), (int((WIDTH - qr_size) / 2), y))
    y += qr_size + 16
    y = _centered(draw, y, hotspot_url, piccolo)

    # Ancorata al fondo, ma mai sopra a quello che la precede: le righe
    # sopra cambiano altezza con la lunghezza dei nomi, e un'etichetta con
    # le due righe sovrapposte non serve a niente.
    _centered(draw, max(y + 40, HEIGHT - MARGIN - 34),
              "Utente: admin    Password: ____________", piccolo)

    return image


def ascii_qr(data):
    """Il QR a caratteri, per chi guarda l'installazione da un terminale."""
    code = qrcode.QRCode(border=1, error_correction=qrcode.constants.ERROR_CORRECT_M)
    code.add_data(data)
    code.make(fit=True)
    from io import StringIO
    buffer = StringIO()
    code.print_ascii(out=buffer, invert=True)
    return buffer.getvalue()


def main():
    parser = argparse.ArgumentParser(description="Etichetta del dispositivo zeroCAM")
    parser.add_argument("--hostname", required=True)
    parser.add_argument("--ssid", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--output", required=True)
    parser.add_argument("--ascii", action="store_true",
                        help="stampa anche il QR della rete a caratteri")
    args = parser.parse_args()

    if args.ascii:
        print(ascii_qr(wifi_payload(args.ssid, args.password)))

    try:
        build(args.hostname, args.ssid, args.password, args.port).save(args.output)
    except OSError as e:
        # L'etichetta è comoda, non indispensabile: i valori sono comunque
        # a video, e l'installazione non deve fallire per un disco pieno.
        print(f"Etichetta non salvata ({e}).", file=sys.stderr)
        return 1

    print(f"Etichetta salvata in {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
