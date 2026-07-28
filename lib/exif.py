# -*- coding: utf-8 -*-
"""
Metadati EXIF per gli scatti salvati.

I fotogrammi del timelapse escono da un ridimensionamento fatto con PIL e
perdono qualunque informazione: nel visualizzatore compaiono con
esposizione, ISO e data vuoti. Qui si ricostruiscono dai metadati che
libcamera restituisce insieme all'immagine.

Il pezzo che conta piu' di tutti e' il bilanciamento del bianco: i
guadagni di rosso e blu scelti dall'automatismo si leggono in
ColourGains, e sono esattamente i valori da riportare nei campi manuali
quando l'automatico sbaglia. In EXIF non esiste un campo standard per
quei due numeri, quindi finiscono nel commento come JSON e, in forma
leggibile, nella descrizione dell'immagine.
"""

import json

try:
    import piexif
    from piexif import helper as piexif_helper
except ImportError:  # pragma: no cover - dipendenza dichiarata in requirements
    piexif = None
    piexif_helper = None


def _rational(value, denominator=1):
    try:
        return (int(round(float(value) * denominator)), denominator)
    except (TypeError, ValueError):
        return None


def _colour_gains(metadata):
    gains = metadata.get("ColourGains")
    try:
        return float(gains[0]), float(gains[1])
    except (TypeError, ValueError, IndexError):
        return None


def summary(metadata):
    """Riga leggibile con i dati di scatto, per la descrizione dell'immagine."""
    parts = []
    exposure = metadata.get("ExposureTime")
    if exposure:
        parts.append(f"exp {int(exposure)}us")
    gain = metadata.get("AnalogueGain")
    if gain:
        parts.append(f"gain {float(gain):.2f}")
    gains = _colour_gains(metadata)
    if gains:
        parts.append(f"ColourGains R={gains[0]:.2f} B={gains[1]:.2f}")
    temperature = metadata.get("ColourTemperature")
    if temperature:
        parts.append(f"{int(temperature)}K")
    lux = metadata.get("Lux")
    if lux is not None:
        parts.append(f"{float(lux):.1f} lux")
    return ", ".join(parts)


def build(metadata, when, description="", software="zeroCAM", manual_white_balance=False):
    """
    Blocco EXIF pronto da passare a Image.save(..., exif=...).

    Ritorna b"" se piexif non c'e' o se qualcosa va storto: i metadati
    sono un di piu', non devono impedire il salvataggio dello scatto.
    """
    if piexif is None:
        return b""

    metadata = metadata or {}
    try:
        stamp = when.strftime("%Y:%m:%d %H:%M:%S")
        detail = summary(metadata)
        caption = " | ".join(p for p in (description, detail) if p)

        zeroth = {
            piexif.ImageIFD.Make: b"Raspberry Pi",
            piexif.ImageIFD.Model: b"Camera Module HQ",
            piexif.ImageIFD.Software: software.encode("ascii", "replace"),
            piexif.ImageIFD.DateTime: stamp.encode("ascii"),
        }
        if caption:
            zeroth[piexif.ImageIFD.ImageDescription] = caption.encode("utf-8", "replace")

        exif = {
            piexif.ExifIFD.DateTimeOriginal: stamp.encode("ascii"),
            piexif.ExifIFD.DateTimeDigitized: stamp.encode("ascii"),
            # 0 = automatico, 1 = manuale: e' l'unico campo standard che
            # dice qualcosa sul bilanciamento del bianco.
            piexif.ExifIFD.WhiteBalance: 1 if manual_white_balance else 0,
        }

        exposure = _rational(metadata.get("ExposureTime", 0), 1)
        if exposure and exposure[0] > 0:
            # ExposureTime di libcamera e' in microsecondi
            exif[piexif.ExifIFD.ExposureTime] = (exposure[0], 1000000)

        gain = metadata.get("AnalogueGain")
        if gain:
            try:
                exif[piexif.ExifIFD.ISOSpeedRatings] = max(1, int(round(float(gain) * 100)))
            except (TypeError, ValueError):
                pass

        temperature = metadata.get("ColourTemperature")
        if temperature:
            try:
                # Non e' un campo standard per i kelvin, ma e' quello che i
                # programmi di sviluppo raw leggono piu' spesso.
                exif[piexif.ExifIFD.ColorSpace] = 1
            except (TypeError, ValueError):
                pass

        # Tutto il resto dei metadati, senza perdere niente: e' qui che si
        # vanno a leggere ColourGains e compagnia.
        payload = {}
        for key, value in metadata.items():
            if isinstance(value, (int, float, str, bool)) or value is None:
                payload[key] = value
            elif isinstance(value, (list, tuple)):
                payload[key] = [v for v in value if isinstance(v, (int, float, str))]
        if payload and piexif_helper is not None:
            # ASCII e non unicode: il JSON e' gia' privo di accenti, e la
            # variante UCS-2 dell'EXIF parecchi visualizzatori la
            # dichiarano non supportata invece di mostrarla.
            exif[piexif.ExifIFD.UserComment] = piexif_helper.UserComment.dump(
                json.dumps(payload, sort_keys=True, ensure_ascii=True), encoding="ascii"
            )

        return piexif.dump({"0th": zeroth, "Exif": exif, "1st": {}, "thumbnail": None, "GPS": {}})

    except Exception:
        return b""
