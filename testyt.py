import subprocess
import select
import time
from picamera2 import Picamera2

# === Config ===
RTMP_URL = "rtmp://a.rtmp.youtube.com/live2/6p2r-g71w-tm6e-tbvq-c6p1"
RESOLUTION = (1280, 720)
FRAMERATE = 15

# === Avvio Camera ===
picam2 = Picamera2()
config = picam2.create_video_configuration(main={"size": RESOLUTION, "format": "RGB888"})
picam2.configure(config)
picam2.start()
time.sleep(2)  # Stabilizzazione

# === Comando ffmpeg ===
ffmpeg_cmd = [
    "ffmpeg",
    "-f", "rawvideo",
    "-pix_fmt", "rgb24",
    "-s", f"{RESOLUTION[0]}x{RESOLUTION[1]}",
    "-r", str(FRAMERATE),
    "-i", "-",
    "-f", "lavfi",
    "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
    "-c:v", "libx264",
    "-preset", "veryfast",
    "-b:v", "2500k",
    "-maxrate", "2500k",
    "-bufsize", "5000k",
    "-pix_fmt", "yuv420p",
    "-g", "60",
    "-c:a", "aac",
    "-ar", "44100",
    "-b:a", "128k",
    "-f", "flv",
    RTMP_URL
]

# === Avvio processo ffmpeg ===
proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE)

print("🚀 Streaming in corso...")
frame_time = 1.0 / FRAMERATE
try:
    while True:
        start = time.time()
        frame = picam2.capture_array("main")

        # Scrivi solo se ffmpeg è pronto
        if select.select([], [proc.stdin], [], 0)[1]:
            try:
                proc.stdin.write(frame.tobytes())
            except BrokenPipeError:
                print("❌ ffmpeg chiuso, fermo lo streaming.")
                break
        else:
            print("⚠️ Frame scartato (ffmpeg occupato)")

        elapsed = time.time() - start
        if elapsed < frame_time:
            time.sleep(frame_time - elapsed)
except KeyboardInterrupt:
    print("⛔ Streaming interrotto manualmente.")
finally:
    picam2.stop()
    proc.stdin.close()
    proc.wait()
    print("✅ Streaming terminato.")

