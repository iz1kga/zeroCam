# -*- coding: utf-8 -*-
"""
Annotazione e loghi sul video in diretta.

Sulla foto ci pensano ImageAnnotator e ImageOverlay con PIL. Sui frame
dello streaming la stessa strada non regge: arrivano come YUV420 grezzo e
ridisegnarli a ogni fotogramma costerebbe più di quanto il Pi possa dare.
ffmpeg però sta già ricodificando, quindi barra, testo, orologio e loghi
si aggiungono con i suoi filtri, prima di x264 e senza passaggi in più.

Le coordinate in configurazione sono in pixel della foto: qui vengono
riscalate per il rapporto fra la larghezza dello streaming e quella dello
scatto, così la diretta somiglia alla foto senza doppie impostazioni.
"""

import hashlib
import os
import urllib.request

from PIL import Image

FONT_PATH = os.path.abspath('static/css/fonts/Arial.ttf')

# Nomi dei file di appoggio scritti nella cartella di lavoro: drawtext li
# legge da disco, così testo e formato data non devono essere sottoposti
# all'escaping del filtergraph.
TEXT_FILE = 'stream_overlay_text.txt'
TIME_FILE = 'stream_overlay_time.txt'


def _escape(value):
    """Protegge un valore dentro la descrizione di un filtro."""
    return str(value).replace('\\', '\\\\').replace(':', '\\:').replace("'", "\\'")


def _rgb(color, default=(255, 255, 255)):
    try:
        return "0x%02X%02X%02X" % (
            int(color.get("R", default[0])) & 0xFF,
            int(color.get("G", default[1])) & 0xFF,
            int(color.get("B", default[2])) & 0xFF,
        )
    except (AttributeError, TypeError, ValueError):
        return "0x%02X%02X%02X" % default


def _alpha(color, key="A", default=255):
    try:
        value = int(color.get(key, default))
    except (AttributeError, TypeError, ValueError):
        value = default
    return round(max(0, min(255, value)) / 255, 3)


def _write(path, content):
    with open(path, 'w') as f:
        f.write(content)
    return path


def _annotation_filters(annotation, scale, work_dir, logger):
    """Barra, testo e orologio, nell'ordine in cui li disegna ffmpeg."""
    content = annotation.get("Content", {}) or {}
    container = annotation.get("Container", {}) or {}

    text = content.get("Text", "") or ""
    dt_format = annotation.get("DTFormat", "") or ""
    if not text and not dt_format:
        return []

    if not os.path.exists(FONT_PATH):
        logger.error(f"Stream overlay font not found at {FONT_PATH}, skipping the annotation.")
        return []

    font_size = max(8, round(int(content.get("FontSize", 30)) * scale))
    offset = max(2, round(int(container.get("Offset", 10)) * scale))
    bar_height = font_size + 2 * offset
    text_y = f"h-{font_size + offset}"
    font_color = f"{_rgb(content.get('Color', {}))}@{_alpha(content.get('Color', {}))}"
    font = _escape(FONT_PATH)

    filters = [
        f"drawbox=x=0:y=ih-{bar_height}:w=iw:h={bar_height}:"
        f"color={_rgb(container, (0, 0, 0))}@{_alpha(container, default=150)}:t=fill"
    ]

    if text:
        path = _escape(_write(os.path.join(work_dir, TEXT_FILE), text))
        filters.append(
            f"drawtext=fontfile={font}:textfile={path}:expansion=none:"
            f"fontsize={font_size}:fontcolor={font_color}:x={offset}:y={text_y}"
        )

    if dt_format:
        # expansion=strftime lascia formattare l'ora a ffmpeg a ogni
        # fotogramma: l'orologio in diretta resta vivo, non congelato
        # all'avvio dello stream.
        path = _escape(_write(os.path.join(work_dir, TIME_FILE), dt_format))
        filters.append(
            f"drawtext=fontfile={font}:textfile={path}:expansion=strftime:"
            f"fontsize={font_size}:fontcolor={font_color}:x=w-tw-{offset}:y={text_y}"
        )

    return filters


def _fetch_logo(url, work_dir, logger):
    """Scarica il logo (se non è già in cache) e ne ritorna path e larghezza."""
    name = f"stream_overlay_logo_{hashlib.sha1(url.encode()).hexdigest()[:12]}.png"
    path = os.path.join(work_dir, name)

    if not os.path.exists(path):
        with urllib.request.urlopen(url, timeout=10) as fd:
            image = Image.open(fd)
            image.load()
        # Il PNG RGBA è il formato che ffmpeg compone senza sorprese
        image.convert("RGBA").save(path, format='PNG')
        logger.info(f"Downloaded stream overlay logo to {path}")

    with Image.open(path) as image:
        return path, image.size[0]


def _logo_filters(overlay_images, scale, work_dir, first_input_index, logger):
    """Un input e una coppia di filtri per ogni logo abilitato."""
    inputs, stages = [], []

    for image_config in overlay_images or []:
        if not image_config.get("enabled") or not image_config.get("url"):
            continue

        name = image_config.get("name", "?")
        try:
            path, source_width = _fetch_logo(image_config["url"], work_dir, logger)
        except Exception as e:
            logger.error(f"Failed to prepare the stream overlay '{name}': {e}")
            continue

        width = round(source_width * int(image_config.get("scale", 100)) / 100 * scale)
        if width < 2:
            logger.warning(f"Stream overlay '{name}' scales down to nothing, skipping it.")
            continue

        index = first_input_index + len(inputs) // 2
        opacity = round(max(0, min(100, int(image_config.get("opacity", 100)))) / 100, 3)
        x = round(int(image_config.get("X", 0)) * scale)
        y = round(int(image_config.get("Y", 0)) * scale)

        inputs.extend(["-i", path])
        stages.append((
            f"[{index}:v]scale={width}:-1,format=rgba,colorchannelmixer=aa={opacity}",
            f"overlay={x}:{y}",
        ))
        logger.info(f"Stream overlay '{name}' at {x},{y} scaled to {width}px wide.")

    return inputs, stages


def build(annotation, overlay_images, stream_size, still_width, work_dir,
          logger, first_input_index=2):
    """
    Argomenti ffmpeg per sovrapporre annotazione e loghi allo streaming.

    Ritorna (inputs, filter_complex, video_label): `inputs` sono gli '-i'
    dei loghi, `video_label` l'uscita video da mappare. Con filter_complex
    None non c'è niente da disegnare e il video resta quello di ingresso.
    """
    default = ([], None, "0:v")
    try:
        stream_width = int(stream_size[0])
        scale = stream_width / int(still_width) if still_width else 1.0
        if scale <= 0:
            scale = 1.0

        os.makedirs(work_dir, exist_ok=True)
        draw = _annotation_filters(annotation or {}, scale, work_dir, logger)
        inputs, logos = _logo_filters(overlay_images, scale, work_dir, first_input_index, logger)
        if not draw and not logos:
            logger.info("Stream overlay enabled but nothing to draw.")
            return default

        label = "0:v"
        stages = []
        if draw:
            stages.append(f"[{label}]{','.join(draw)}[ovl0]")
            label = "ovl0"

        for i, (prepare, compose) in enumerate(logos, start=1):
            stages.append(f"{prepare}[lg{i}]")
            stages.append(f"[{label}][lg{i}]{compose}[ovl{i}]")
            label = f"ovl{i}"

        logger.info(f"Stream overlay ready (scale {scale:.3f} from the still image).")
        return inputs, ";".join(stages), f"[{label}]"

    except Exception as e:
        logger.error(f"Failed to build the stream overlay: {e}", exc_info=True)
        return default
