# -*- coding: utf-8 -*-
"""
Genera gli screenshot dell'interfaccia per il manuale.

Serve i template, gli static e le pagine veri dell'applicazione con un
backend finto: quello che si vede e' l'interfaccia che vedra' l'utente,
i dati sono di esempio. Cosi' gli screenshot si rifanno a ogni modifica
senza toccare la webcam e senza che finiscano segreti nel PDF.

    python uishots.py v1.1.4-rc7
"""

import io
import json
import os
import sys
import threading
import time

from flask import Flask, Response, jsonify, render_template, send_file, send_from_directory

REPO = "/home/mgiolo/Personale/repos/zeroCam"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shots")
VERSION = sys.argv[1] if len(sys.argv) > 1 else "v1.1.4"
PORT = 8931

sys.path.insert(0, REPO)
from lib.components.config_manager import DEFAULT_SECTIONS  # noqa: E402

app = Flask(__name__,
            template_folder=os.path.join(REPO, "templates"),
            static_folder=os.path.join(REPO, "static"))
app.context_processor(lambda: {"version": VERSION})

CONFIG = json.load(open(os.path.join(REPO, ".conf.json")))
for section, defaults in DEFAULT_SECTIONS.items():
    current = CONFIG.setdefault(section, {})
    for key, value in defaults.items():
        current.setdefault(key, value)

# Valori di esempio: plausibili come in un impianto vero, ma inventati.
CONFIG["deviceDetails"].update(name="Villar Focchiardo - Borgata Comba")
CONFIG["streamParameters"].update(
    enabled=True, width=2560, height=1440,
    yt_api_key="chiave-di-streaming", overlay=True,
    extra_destinations=["rtmp://live.twitch.tv/app/live_000000_esempio"],
    audio_file="asset:audio/default_stream_audio.mp3", audio_volume=25,
)
CONFIG["youtubeLive"].update(
    enabled=True, client_id="000000000000-esempio.apps.googleusercontent.com",
    client_secret="segreto", refresh_token="token",
    title="Villar Focchiardo - Live Webcam {date}",
    description="Vista verso est dalla Borgata Comba",
    daily_reset_time="00:00",
)
CONFIG["timelapse"].update(
    enabled=True, retention_weeks=4, min_frames=200,
    title="Timelapse {from} - {to}", description="Una settimana in un minuto",
    audio_file="asset:audio/brano-di-sottofondo.mp3", audio_volume=30,
)
CONFIG["OverlayImages"] = [
    {"enabled": True, "name": "Logo TorinoMeteo", "url": "asset:logo/TMLogo.png",
     "X": 3780, "Y": 15, "scale": 220, "opacity": 80},
    {"enabled": True, "name": "Logo zeroCAM", "url": "asset:logo/ZC_logo_alfa.png",
     "X": 25, "Y": 25, "scale": 250, "opacity": 80},
]
CONFIG["Annotation"]["Content"]["Text"] = "Villar Focchiardo (TO) - Borgata Comba"
CONFIG["settingsManager"].update(https_enabled=True, https_hostnames=["webcam.esempio.it"])

ASSETS = [
    {"category": "audio", "name": "default_stream_audio.mp3",
     "reference": "asset:audio/default_stream_audio.mp3", "size": 1445528, "modified": 0},
    {"category": "audio", "name": "brano-di-sottofondo.mp3",
     "reference": "asset:audio/brano-di-sottofondo.mp3", "size": 3211264, "modified": 0},
    {"category": "logo", "name": "TMLogo.png",
     "reference": "asset:logo/TMLogo.png", "size": 18422, "modified": 0},
    {"category": "logo", "name": "ZC_logo_alfa.png",
     "reference": "asset:logo/ZC_logo_alfa.png", "size": 3110, "modified": 0},
]

# Una foto vera dell'impianto, gia' presente fra le immagini del manuale
PHOTO = os.path.join(REPO, "doc", "img", "foto-annotata.png")

def _roi(id, mode, box):
    x0, y0, x1, y1 = box
    return {"id": id, "mode": mode,
            "points": [{"x": x0, "y": y0}, {"x": x1, "y": y0},
                       {"x": x1, "y": y1}, {"x": x0, "y": y1}]}


ROIS = [_roi(1, "blur", (28.0, 79.0, 42.0, 92.0)),
        _roi(2, "filled", (61.0, 74.0, 72.0, 86.0))]

DAYS = [{"day": "2026-07-28", "count": 61}, {"day": "2026-07-27", "count": 144},
        {"day": "2026-07-26", "count": 144}, {"day": "2026-07-25", "count": 144}]
FRAMES = [f"20260728-{h:02d}{m:02d}00.jpg" for h in range(6, 16) for m in (0, 10, 20, 30, 40, 50)]

LOG = "\n".join([
    "2026-07-28 10:40:01,102 - SchedulerThread - INFO - Capture job scheduled every 600 seconds.",
    "2026-07-28 10:40:02,455 - Thread-3 (capture_job) - INFO - --- Inizio cattura per 'day' ---",
    "2026-07-28 10:40:02,470 - Thread-3 (capture_job) - INFO - Modalita' diurna: uso l'esposizione automatica (AeEnable=True).",
    "2026-07-28 10:40:02,471 - Thread-3 (capture_job) - INFO - Bilanciamento del bianco automatico, modalita' 5",
    "2026-07-28 10:40:04,613 - Thread-3 (capture_job) - INFO - Cattura diurna completata in 2.1s. Gain: 1.00, Esposizione: 0.0002s",
    "2026-07-28 10:40:05,004 - Thread-3 (capture_job) - INFO - Loaded 2 privacy mask(s).",
    "2026-07-28 10:40:05,880 - Thread-3 (capture_job) - INFO - Added Logo TorinoMeteo at 3780, 15",
    "2026-07-28 10:40:06,120 - Thread-3 (capture_job) - INFO - Uploading to upload.esempio.it",
    "2026-07-28 10:40:09,455 - Thread-3 (capture_job) - INFO - Capture job finished in 7.0s.",
    "2026-07-28 10:40:10,201 - Thread-3 (capture_job) - INFO - Reusing YouTube broadcast Ab12Cd34 (started after the daily reset of 28/07/2026 00:00).",
    "2026-07-28 10:40:10,890 - YouTubeStreamThread - INFO - Audio dello streaming: default_stream_audio.mp3 al 25% di volume.",
    "2026-07-28 10:40:11,002 - YouTubeStreamThread - INFO - Restreaming to 2 destinations: a.rtmp.youtube.com, live.twitch.tv",
])


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/view/pages/<page_name>")
def page(page_name):
    return send_from_directory(os.path.join(REPO, "templates", "pages"), page_name)


@app.route("/api/config")
def api_config():
    return jsonify(CONFIG)


@app.route("/api/schema")
def api_schema():
    return jsonify(json.load(open(os.path.join(REPO, "config_schema.json"))))


@app.route("/api/assets")
def api_assets():
    return jsonify(success=True, assets=ASSETS, categories={"audio": "Audio", "logo": "Loghi"})


@app.route("/assets/<category>/<name>")
def asset_file(category, name):
    return send_from_directory(os.path.join(REPO, "static", "brand"), "zc_logo_primary.png")


@app.route("/latest.jpg")
@app.route("/stream_latest.jpg")
@app.route("/timelapse/frame/<name>")
def photo(name=None):
    return send_file(PHOTO, mimetype="image/jpeg")


@app.route("/api/privacy_mask")
def api_mask():
    return jsonify(ROIS)


@app.route("/api/status/capture")
def status_capture():
    return jsonify(is_capturing=False, elapsed=0)


@app.route("/api/status/stream")
def status_stream():
    return jsonify(running=True)


@app.route("/api/timelapse")
def api_timelapse():
    return jsonify(frames=1008, bytes=1104224256, oldest="20260721-060000.jpg",
                   newest="20260728-153000.jpg",
                   last_result={"status": "ok", "when": "2026-07-27 03:12",
                                "frames": 1002, "video": "timelapse-20260727-031204.mp4",
                                "url": "https://youtu.be/esempio"})


@app.route("/api/timelapse/frames")
def api_frames():
    from flask import request
    day = request.args.get("day")
    if not day:
        return jsonify(days=DAYS)
    return jsonify(day=day, frames=FRAMES)


@app.route("/api/log")
def api_log():
    return Response(LOG, mimetype="text/plain")


@app.route("/api/stats")
def api_stats():
    now = time.time()
    import math
    history = []
    for i in range(60):
        wave = math.sin(i / 9.0) + 0.35 * math.sin(i / 2.3)
        temp = 55 + 3.5 * wave
        cpu = 19 + 6 * math.sin(i / 7.0 + 1.2) + 2 * math.sin(i / 1.7)
        history.append({
            "timestamp": now - (60 - i) * 60,
            "cpuTemperature": {"min": round(temp - 3.2, 1), "max": round(temp + 4.1, 1),
                               "average": round(temp, 1)},
            "cpuUsage": {"min": round(max(0.5, cpu - 14), 1), "max": round(cpu + 11, 1),
                         "average": round(cpu, 1)},
        })
    return jsonify(latest={"cpuTemperature": 56.8, "cpuUsage": 25.6, "diskUsage": 22.3,
                           "memoryUsage": 25.5, "loadAverage": [0.96, 1.0, 0.96],
                           "timestamp": now},
                   history=history)


PAGES = [
    ("ui-cam-control", "control", None),
    ("ui-status", "status", None),
    ("ui-timelapse-galleria", "timelapse", None),
    ("ui-system-backup", "system", None),
    ("ui-config-camera", "config", "cameraParameters"),
    ("ui-config-stream", "config", "streamParameters"),
    ("ui-config-timelapse", "config", "timelapse"),
    ("ui-config-annotation", "config", "annotation"),
    ("ui-config-overlays", "config", "overlayImages"),
    ("ui-config-assets", "config", "assets"),
]


def capture():
    from playwright.sync_api import sync_playwright

    os.makedirs(OUT, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1920, "height": 961})
        for name, main, sub in PAGES:
            page.goto(f"http://127.0.0.1:{PORT}/", wait_until="load")
            page.wait_for_selector(".sidebar")
            page.evaluate(
                """([main, sub]) => {
                    const vm = document.querySelector('#app').__vue_app__._instance.proxy;
                    vm.page = main;
                    if (sub) vm.configPage = sub;
                }""", [main, sub])
            # Grafici e immagini hanno bisogno di un attimo per comparire
            page.wait_for_timeout(2500)
            page.screenshot(path=os.path.join(OUT, name + ".png"))
            print("scritto", name)
        browser.close()


if __name__ == "__main__":
    threading.Thread(target=lambda: app.run(port=PORT, threaded=True), daemon=True).start()
    time.sleep(1.5)
    capture()
