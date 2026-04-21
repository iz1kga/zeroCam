from flask import Flask, Response
from picamera2 import Picamera2
from PIL import Image, ImageDraw, ImageFont
import io
import time

app = Flask(__name__)

# Inizializza la fotocamera
picam2 = Picamera2()
picam2.configure(picam2.create_still_configuration(main={"size": (4056, 3040)}))  # Cambia la risoluzione qui
picam2.start()

frame_counter = 0  # Contatore dei frame

def generate_frames():
    """ Cattura un'immagine, aggiunge il contatore e la trasmette in MJPEG """
    global frame_counter
    stream = io.BytesIO()

    while True:
        stream.seek(0)
        stream.truncate()

        picam2.capture_file(stream, format="jpeg")
        stream.seek(0)

        image = Image.open(stream)
        draw = ImageDraw.Draw(image)

        try:
            # Ho ridotto la dimensione del font per renderlo più gestibile
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 60)
        except:
            font = ImageFont.load_default()

        frame_counter += 1
        text = f"Frame: {frame_counter}"
        
        # --- INIZIO MODIFICA ---

        # 1. Definisci la posizione del testo
        text_position = (50, 50)

        # 2. Calcola le dimensioni del box di sfondo (opzionale ma consigliato)
        #    bbox ti dà (left, top, right, bottom) del testo
        text_bbox = draw.textbbox(text_position, text, font=font)
        # Aggiungiamo un po' di padding per un look migliore
        box_padding = 10
        background_box = (
            text_bbox[0] - box_padding,
            text_bbox[1] - box_padding,
            text_bbox[2] + box_padding,
            text_bbox[3] + box_padding
        )

        # 3. Disegna il rettangolo nero come sfondo per il testo
        draw.rectangle(background_box, fill="black")

        # 4. Ora disegna il testo sopra il rettangolo (con un colore a contrasto)
        draw.text(text_position, text, fill="white", font=font)

        # --- FINE MODIFICA ---

        stream.seek(0)
        image.save(stream, format="JPEG")
        frame_bytes = stream.getvalue()

        yield (b"--frame\r\n"
               b"Content-Type: image/jpeg\r\n\r\n" +
               frame_bytes + b"\r\n")

        time.sleep(0.1)


@app.route('/stream')
def stream():
    """ Endpoint per lo streaming MJPEG """
    return Response(generate_frames(), mimetype="multipart/x-mixed-replace; boundary=frame")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, threaded=True)

