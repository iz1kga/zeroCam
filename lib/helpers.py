from ftplib import FTP
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont, ExifTags, ImageFilter
from PIL.TiffImagePlugin import ImageFileDirectory_v2
from datetime import datetime, timezone
import ephem
from string import Template
import tzlocal
import urllib.request
from urllib.error import URLError
import io
import psutil
import os
import base64
import requests
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import json
import logging
import cv2
import numpy as np

from lib import assets
from lib.paths import LATEST_IMAGE, PRIVACY_MASK_FILE as PRIVACY_MASK_PATH


def load_privacy_rois(logger=None):
    """Carica le ROI delle privacy mask, ritornando una lista vuota se assenti."""
    logger = logger or logging.getLogger(__name__)
    try:
        with open(PRIVACY_MASK_PATH, 'r') as f:
            rois = json.load(f)
            logger.info(f"Loaded {len(rois)} privacy mask(s) from {PRIVACY_MASK_PATH}.")
            return rois
    except FileNotFoundError:
        logger.info(f"{PRIVACY_MASK_PATH} not found. No privacy masks will be applied.")
        return []
    except json.JSONDecodeError:
        logger.error(f"{PRIVACY_MASK_PATH} is corrupted. Could not load privacy masks.")
        return []
    except Exception as e:
        logger.error(f"An unexpected error occurred while loading ROIs: {e}")
        return []


def centered_view(source_view, target_aspect):
    """Ritaglio centrato, del formato richiesto, più ampio possibile dentro source_view."""
    x, y, w, h = source_view
    if not h or not target_aspect:
        return source_view
    if (w / h) > target_aspect:
        new_w, new_h = h * target_aspect, h
    else:
        new_w, new_h = w, w / target_aspect
    return (x + (w - new_w) / 2.0, y + (h - new_h) / 2.0, new_w, new_h)


def remap_rois_to_view(rois, source_view, target_view, logger=None):
    """
    Riporta le ROI dalla vista su cui sono state disegnate a un'altra vista.

    Le ROI sono in percentuale dell'immagine su cui l'utente le ha
    tracciate (la foto, eventualmente ritagliata). La foto e lo streaming
    hanno formati diversi e coprono porzioni diverse del sensore, quindi
    le stesse percentuali indicano punti diversi della scena. Entrambe le
    viste sono espresse in coordinate del sensore, l'unico riferimento
    comune, e le ROI vengono convertite di conseguenza.

    Le viste sono rettangoli (x, y, w, h) in coordinate del sensore.
    """
    logger = logger or logging.getLogger(__name__)
    if not rois or not source_view or not target_view:
        return rois

    sx, sy, sw, sh = source_view
    tx, ty, tw, th = target_view
    if not sw or not sh or not tw or not th:
        logger.warning("Invalid sensor views, privacy masks left unscaled.")
        return rois
    if (sx, sy, sw, sh) == (tx, ty, tw, th):
        return rois

    remapped = []
    for roi in rois:
        points = roi.get('points') or []
        remapped.append({**roi, 'points': [
            {
                'x': ((sx + (p['x'] / 100.0) * sw) - tx) / tw * 100.0,
                'y': ((sy + (p['y'] / 100.0) * sh) - ty) / th * 100.0,
            }
            for p in points
        ]})

    logger.info(f"Privacy masks remapped from sensor view {source_view} to {target_view}.")
    return remapped


def split_rois_by_mode(rois):
    """Separa le ROI fra quelle da sfocare e quelle da coprire completamente."""
    blur, filled = [], []
    for roi in rois or []:
        points = roi.get('points')
        if not points or len(points) < 3:
            continue
        (filled if roi.get('mode') == 'filled' else blur).append(points)
    return blur, filled

class CryptoHelper:
    def __init__(self, secret_key, logger):
        self.logger = logger
        if not secret_key:
            self.logger.error("La chiave segreta non può essere vuota.")
            raise ValueError("Secret key cannot be empty.")
        self.key = self._derive_key(secret_key)
        self.fernet = Fernet(self.key)

    def _derive_key(self, secret_key):
        """Deriva una chiave di crittografia a 32 byte dalla chiave segreta fornita."""
        # Usiamo un salt fisso ma questo è accettabile perché la chiave segreta è unica per installazione
        salt = b'zerocam-salt'
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        return base64.urlsafe_b64encode(kdf.derive(secret_key.encode()))

    def encrypt(self, plaintext):
        if not isinstance(plaintext, str):
            plaintext = str(plaintext)
        encrypted = self.fernet.encrypt(plaintext.encode())
        return "enc:" + encrypted.decode()

    def decrypt(self, ciphertext):
        if not ciphertext.startswith("enc:"):
            # Se la stringa non è criptata, la restituisce così com'è
            return ciphertext
        
        try:
            encrypted_part = ciphertext[4:]
            decrypted = self.fernet.decrypt(encrypted_part.encode())
            return decrypted.decode()
        except Exception as e:
            self.logger.error(f"Errore durante la decrittografia: {e}. Controllare che ZEROCAM_SECRET_KEY sia corretta.", exc_info=True)
            # In caso di errore (es. chiave errata), restituisce la stringa originale per evitare crash
            return ciphertext

class FTPUploader:
    def __init__(self, ftp_host, logger):
        self.logger = logger
        self.ftp_host = ftp_host
        self.logger.info("FTPUploader object created")

    def update_config(self, ftp_host):
        """Nuova destinazione FTP dallo scatto successivo."""
        self.ftp_host = ftp_host or {}

    def upload(self, image, metadata):
        try:
            self.logger.info(f"Uploading to {self.ftp_host['host']}")
            ftp = FTP()
            ftp.connect(self.ftp_host['host'], self.ftp_host['port'], timeout=self.ftp_host['timeout'])
            ftp.login(user=self.ftp_host['username'], passwd=self.ftp_host['password'])
            ftp.cwd(self.ftp_host['folder'])
            ftp.set_pasv(True)  # Ensure passive mode is used
            ftp.storbinary(f'STOR {self.ftp_host["filename"]}', image)
            ftp.quit()
            self.logger.info(f"Uploaded to {self.ftp_host['host']}")
        except Exception as e:
            self.logger.error(f"Failed to upload to {self.ftp_host['host']}: {e}")


class HttpUploader:
    def __init__(self, http_config, logger):
        self.logger = logger
        self.cfg = http_config or {}
        self.logger.info("HttpUploader object created")

    def update_config(self, http_config):
        """Nuovo endpoint HTTP dallo scatto successivo."""
        self.cfg = http_config or {}

    def upload(self, image, metadata):
        if not self.cfg.get("enabled"):
            return

        url = self.cfg.get("url")
        token = self.cfg.get("token")
        if not url or not token:
            self.logger.warning("HttpUploader enabled but url/token missing, skipping upload.")
            return

        try:
            image.seek(0)
            files = {"image": ("webcam.jpg", image, "image/jpeg")}
            data = {}
            if self.cfg.get("send_timestamp", True):
                data["timestamp"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

            self.logger.info(f"HTTP upload to {url}")
            r = requests.post(
                url,
                headers={"Authorization": f"Bearer {token}"},
                files=files,
                data=data,
                timeout=self.cfg.get("timeout", 30),
            )

            if r.status_code == 201:
                self.logger.info(f"HTTP upload OK: {r.json()}")
                return

            # Error handling by documented codes
            try:
                payload = r.json()
                code = payload.get("code", "")
            except Exception:
                payload = r.text
                code = ""

            if r.status_code == 409 or code == "DUPLICATE_DATA":
                self.logger.warning(f"HTTP upload duplicate (409): {payload}")
            elif r.status_code == 401:
                self.logger.error(f"HTTP upload unauthorized (401): check token. {payload}")
            elif r.status_code == 403:
                self.logger.error(f"HTTP upload forbidden (403) — webcam disabled server-side. {payload}")
            elif r.status_code == 400:
                self.logger.error(f"HTTP upload bad request (400): {payload}")
            else:
                self.logger.error(f"HTTP upload failed status={r.status_code}: {payload}")
        except requests.exceptions.RequestException as e:
            self.logger.error(f"HTTP upload network error: {e}")
        except Exception as e:
            self.logger.error(f"HTTP upload unexpected error: {e}", exc_info=True)

class ImageOverlay:
    def __init__(self, OverlayImages, logger):
        self.logger = logger
        self.logger.info("ImageOverlay object created")
        self.update_config(OverlayImages)

    def update_config(self, OverlayImages):
        """
        Nuovo elenco di loghi, riscaricati subito.

        Le voci vengono copiate perché downloadImages ci infila dentro
        l'immagine PIL: lavorando sui dizionari della configurazione, quella
        finirebbe dentro la configurazione stessa, che poi non sarebbe più
        serializzabile in JSON per l'interfaccia web.
        """
        self.OverlayImages = [dict(item) for item in OverlayImages or []]
        self.downloadImages()

    def downloadImages(self):
        self.logger.info("Downloading overlay images")
        for OverlayImage in self.OverlayImages:
            if not OverlayImage["enabled"]:
                continue
            try:
                # Un logo scelto fra gli assets è un file locale: resolve_url
                # lo trasforma in un file://, gli URL http restano tali.
                fd = urllib.request.urlopen(assets.resolve_url(OverlayImage["url"]))
                OlImg = io.BytesIO(fd.read())
                # RGBA anche per i formati senza trasparenza: serve un canale
                # alfa su cui applicare l'opacità configurata.
                OverlayImage["image"] = Image.open(OlImg).convert("RGBA")
                self.logger.info(f"Downloaded {OverlayImage['name']}")
            except Exception as e:
                self.logger.error(f"Failed to download {OverlayImage['name']} from {OverlayImage['url']}: {e}")
        
    @staticmethod
    def _with_opacity(image, opacity):
        """
        Scala il canale alfa del logo per l'opacità configurata (0-100).

        La trasparenza del PNG resta rispettata: l'opacità la moltiplica,
        come fa colorchannelmixer sullo streaming.
        """
        try:
            percent = max(0, min(100, int(opacity)))
        except (TypeError, ValueError):
            percent = 100
        if percent >= 100:
            return image

        image = image.convert("RGBA")
        alpha = image.getchannel("A").point(lambda a: round(a * percent / 100))
        image.putalpha(alpha)
        return image

    def add_overlays(self, image_buffer):
        try:
            image = Image.open(image_buffer)
        except Exception as e:
            self.logger.error(f"Failed to open image buffer: {e}")
            return image_buffer
        self.logger.info("Adding overlays")
        for OverlayImage in self.OverlayImages:
            if not OverlayImage["enabled"]:
                continue
            try:
                # Si lavora su una copia: thumbnail() ridimensiona in place e
                # sull'originale in cache lo scatto successivo ripartirebbe da
                # un logo già rimpicciolito.
                olImg = OverlayImage["image"].copy()
                width, height = olImg.size
                width = width * int(OverlayImage["scale"])/100
                height = height * int(OverlayImage["scale"])/100
                olImg.thumbnail((width, height), Image.LANCZOS)
                olImg = self._with_opacity(olImg, OverlayImage.get("opacity", 100))
                image.paste(olImg, (OverlayImage["X"], OverlayImage["Y"]), olImg)
                self.logger.info(f"Added {OverlayImage['name']} at {OverlayImage['X']}, {OverlayImage['Y']}")
            except Exception as e:
                self.logger.error(f"Failed to add {OverlayImage['name']}: {e}")
        out_buffer = BytesIO()
        try:
            image.save(out_buffer, format='JPEG')
            out_buffer.seek(0)
            return out_buffer
        except Exception as e:
            self.logger.error(f"Failed to save image: {e}")
            return image_buffer

class ImageCropper:
    def __init__(self, crop_settings, logger):
        self.logger = logger
        self.crop_settings = crop_settings
        self.logger.info("ImageCropper object created")

    def update_config(self, crop_settings):
        self.crop_settings = crop_settings
        self.logger.info("ImageCropper configuration updated")

    def crop(self, image_buffer):
        self.logger.info("Cropping image")
        if not self.crop_settings["enabled"]:
            return image_buffer
        try:
            image = Image.open(image_buffer)
            width, height = image.size
            new_width = self.crop_settings["width"]
            new_height = self.crop_settings["height"]
            x_offset = self.crop_settings["x_offset"]
            y_offset = self.crop_settings["y_offset"]

            if new_width > width or new_height > height:
                self.logger.warning("Crop size is larger than the image size. Skipping cropping.")
                return image_buffer

            left = (width - new_width) / 2 + x_offset
            top = (height - new_height) / 2 + y_offset
            right = (width + new_width) / 2 + x_offset
            bottom = (height + new_height) / 2 + y_offset

            # Ensure the crop box is within the image bounds
            left = max(0, left)
            top = max(0, top)
            right = min(width, right)
            bottom = min(height, bottom)

            cropped_image = image.crop((left, top, right, bottom))
            out_buffer = BytesIO()
            cropped_image.save(out_buffer, format='JPEG')
            out_buffer.seek(0)
            return out_buffer
        except Exception as e:
            self.logger.error(f"Failed to crop image: {e}")
            return image_buffer

class ImageAnnotator:
    def __init__(self, annotation, logger):
        self.logger = logger
        self.update_config(annotation)

    def update_config(self, annotation):
        """Testo, colori e formato della data dallo scatto successivo."""
        self.annotation = annotation or {}
        self.content = self.annotation.get('Content', {})
        self.container = self.annotation.get('Container', {})

    def annotate(self, image_buffer):
        try:
            self.logger.info("Annotating image")
            image = Image.open(image_buffer)
            draw = ImageDraw.Draw(image, "RGBA")
            draw.rectangle((0, image.size[1] - (self.content["FontSize"] + 2 * self.container["Offset"]), image.size[0], image.size[1]),
                   fill=(int(self.container["R"]), 
                     int(self.container["G"]), 
                     int(self.container["B"]), 
                     int(self.container["A"])))
            fnt = ImageFont.truetype('static/css/fonts/Arial.ttf', self.content["FontSize"])

            annotationText = self.content["Text"]

            draw.text((10, image.size[1] - (self.content["FontSize"] + self.container["Offset"])),
                  annotationText,
                  font=fnt,
                  fill=(int(self.content["Color"]["R"]), 
                    int(self.content["Color"]["G"]), 
                    int(self.content["Color"]["B"]), 
                    int(self.content["Color"]["A"])))
            current_time = datetime.now()
            DTText = current_time.strftime(self.annotation["DTFormat"])

            bbox = draw.textbbox((0, 0), DTText, font=fnt)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]

            draw.text((image.size[0] - text_width - self.container["Offset"], image.size[1] - (self.content["FontSize"] + self.container["Offset"])),
                  DTText,
                  font=fnt,
                  fill=(int(self.content["Color"]["R"]), 
                    int(self.content["Color"]["G"]), 
                    int(self.content["Color"]["B"]), 
                    int(self.content["Color"]["A"])))

            out_buffer = BytesIO()
            image.save(out_buffer, format='JPEG')
            out_buffer.seek(0)
            return out_buffer
        except Exception as e:
            self.logger.error(f"Failed to annotate image: {e}")
            return image_buffer
    
class DayPeriodCalculator:
    def __init__(self, latitude, longitude, elevation, sun_rise_offset, sun_set_offset, dusk_offset, dawn_offset, logger):
        self.tz_info = tzlocal.get_localzone()
        self.logger = logger
        self.update_config(latitude, longitude, elevation,
                           sun_rise_offset, sun_set_offset, dusk_offset, dawn_offset)

    def update_config(self, latitude, longitude, elevation,
                      sun_rise_offset, sun_set_offset, dusk_offset, dawn_offset):
        """Posizione e scarti delle fasi, dal calcolo successivo."""
        self.latitude = latitude
        self.longitude = longitude
        self.elevation = elevation
        self.sun_rise_offset = sun_rise_offset
        self.sun_set_offset = sun_set_offset
        self.dusk_offset = dusk_offset
        self.dawn_offset = dawn_offset

    def get_day_period(self, ):
        try:
            date_time = datetime.now(self.tz_info)

            observer = ephem.Observer()
            observer.lat = str(self.latitude)
            observer.lon = str(self.longitude)
            observer.elev = self.elevation
            observer.date = date_time.strftime("%Y/%m/%d") + " 00:00:01"
            observer.horizon = '0'
            self.logger.debug(f"Observer: {observer}")

            # Calculate the sun position
            sun = ephem.Sun(observer)

            # No offset sunrise sunset
            self.no_offset_sunrise = observer.next_rising(sun).datetime().replace(tzinfo=timezone.utc).astimezone(self.tz_info)
            self.no_offset_sunset = observer.next_setting(sun).datetime().replace(tzinfo=timezone.utc).astimezone(self.tz_info)

            # Calculate sunrise and sunset times
            observer.horizon = str(self.sun_rise_offset)
            self.sunrise = observer.next_rising(sun).datetime().replace(tzinfo=timezone.utc).astimezone(self.tz_info)

            observer.horizon = str(self.sun_set_offset)
            self.sunset = observer.next_setting(sun).datetime().replace(tzinfo=timezone.utc).astimezone(self.tz_info)

            observer.horizon = str(self.dawn_offset)
            self.dawn = observer.next_rising(sun).datetime().replace(tzinfo=timezone.utc).astimezone(self.tz_info)

            observer.horizon = str(self.dusk_offset)
            self.dusk = observer.next_setting(sun).datetime().replace(tzinfo=timezone.utc).astimezone(self.tz_info)

            # Log calculated times
            self.logger.debug(f"Dawn: {self.dawn}")
            self.logger.debug(f"Sunrise: {self.sunrise}")
            self.logger.debug(f"Sunset: {self.sunset}")
            self.logger.debug(f"Dusk: {self.dusk}")

            # Determine the current period of the day
            dayperiod = "unknown"
            if self.dawn <= date_time < self.sunrise:
                dayperiod = "dawn"
            if self.sunrise <= date_time < self.sunset:
                dayperiod = "day"
            if self.sunset <= date_time < self.dusk:
                dayperiod = "dusk"
            if date_time >= self.dusk or date_time < self.dawn:
                dayperiod = "night"
            self.logger.debug(f"Dayperiod is: {dayperiod}")
            return dayperiod
        except Exception as e:
            self.logger.error(f"Failed to calculate day period: {e}")
            return "unknown"

# functions
def saveImage(logger, image_buffer):
    image = Image.open(image_buffer)
    image.save(LATEST_IMAGE, format="JPEG")

def unsharpMask(logger, image_buffer, radius=3, percent=75, threshold=5):
    image = Image.open(image_buffer)
    sharpened_image = image.filter(ImageFilter.UnsharpMask(radius=radius, percent=percent, threshold=threshold))
    out_buffer = BytesIO()
    image.save(out_buffer, format='JPEG')
    out_buffer.seek(0)
    return out_buffer


def logRecursive(logger, data, indent=2):
    if isinstance(data, dict):  # If data is a dictionary, recurse over its items
        for key, value in data.items():
            # Mask sensitive information
            if ["pwd", "password", "pass"].count(key.lower()) > 0:
                value = "*****"
            
            # If value is a dictionary, recurse into it
            if isinstance(value, dict):
                logger.info("  " * indent + f"{key}:")
                logRecursive(logger, value, indent + 1)
            # If value is a list, iterate over it
            elif isinstance(value, list):
                logger.info("  " * indent + f"{key}:")
                for i, item in enumerate(value):
                    logger.info("  " * (indent + 1) + f"[{i}]:")
                    if isinstance(item, dict):
                        logRecursive(logger, item, indent + 2)
                    else:
                        logger.info("  " * (indent + 2) + str(item))
            # If value is a primitive type, log it
            else:
                logger.info("  " * indent + f"{key}: {value}")
    
    elif isinstance(data, list):  # If data is a list, iterate over its items
        for i, item in enumerate(data):
            logger.info("  " * (indent + 1) + f"[{i}]:")
            logRecursive(logger, item, indent + 2)

    else:  # If data is a primitive type (e.g., int, float, string), log it directly
        logger.info("  " * indent + str(data))


def check_internet_connection():
    try:
        urllib.request.urlopen('https://www.google.com', timeout=5)
        return True
    except URLError:
        return False

def get_raspberry_pi_stats():
    # CPU temperature
    try:
        temp = os.popen("cat /sys/class/thermal/thermal_zone0/temp").readline()
        cpu_temp = float(temp)/1000
    except:
        cpu_temp = "Unavailable"

    # CPU usage
    cpu_usage = psutil.cpu_percent(interval=1)

    # Memory usage
    memory_info = psutil.virtual_memory()
    memory_usage = memory_info.percent

    # Disk usage
    disk_info = psutil.disk_usage('/')
    disk_usage = disk_info.percent

    # CPU load average
    load_avg = os.getloadavg()  # Returns 1, 5, and 15 minute load averages

    stats = {
        "cpuTemperature": cpu_temp,
        "cpuUsage": cpu_usage,
        "memoryUsage": memory_usage,
        "diskUsage": disk_usage,
        "loadAverage": load_avg
    }
    return stats


def _polygon_mask(size, polygons):
    """Rasterizza dei poligoni (punti in percentuale) su una maschera 'L'."""
    width, height = size
    mask = Image.new('L', size, 0)
    draw = ImageDraw.Draw(mask)
    for points in polygons:
        draw.polygon(
            [((p['x'] / 100.0) * width, (p['y'] / 100.0) * height) for p in points],
            fill=255
        )
    return mask


class PrivacyMasker:
    """
    Applies privacy masks to an image, either blurring or completely
    covering the polygonal regions defined in a JSON file.
    """
    def __init__(self, blur_radius=10, logger=None):
        """
        Initializes the PrivacyMasker.

        Args:
            blur_radius (int): The radius for the Gaussian blur effect.
            logger: An optional logger instance.
        """
        self.logger = logger or logging.getLogger(__name__)
        self.blur_radius = blur_radius
        self.rois = self._load_rois()

    def _load_rois(self):
        return load_privacy_rois(self.logger)

    def apply_masks(self, image_buffer):
        self.rois = self._load_rois()  # Reload ROIs in case the file has changed
        blur_polygons, filled_polygons = split_rois_by_mode(self.rois)
        if not blur_polygons and not filled_polygons:
            return image_buffer

        try:
            self.logger.info("Applying privacy masks to image...")
            original_image = Image.open(image_buffer)
            size = original_image.size

            if blur_polygons:
                blurred_image = original_image.filter(ImageFilter.GaussianBlur(radius=self.blur_radius))
                original_image.paste(blurred_image, (0, 0), _polygon_mask(size, blur_polygons))

            if filled_polygons:
                opaque = Image.new(original_image.mode, size, 0)
                original_image.paste(opaque, (0, 0), _polygon_mask(size, filled_polygons))

            out_buffer = io.BytesIO()
            original_image.save(out_buffer, format='JPEG')
            out_buffer.seek(0)

            self.logger.info("Privacy masks applied successfully.")
            return out_buffer

        except Exception as e:
            self.logger.error(f"Failed to apply privacy masks: {e}", exc_info=True)
            return image_buffer


class FramePrivacyMasker:
    """
    Applica le privacy mask ai frame video grezzi (array numpy) invece che
    a un JPEG.

    I poligoni vengono rasterizzati una sola volta alla risoluzione del
    frame: per ogni fotogramma resta solo un'indicizzazione booleana, così
    il costo regge il framerate dello streaming. La sfocatura è ottenuta
    riducendo e reingrandendo la regione interessata, molto più economica
    di una gaussiana a piena risoluzione e visivamente equivalente.
    """

    def __init__(self, rois, width, height, blur_radius=10, logger=None):
        self.logger = logger or logging.getLogger(__name__)
        self.width = width
        self.height = height
        self.factor = max(2, int(blur_radius))

        blur_polygons, filled_polygons = split_rois_by_mode(rois)
        self.blur_mask = np.array(_polygon_mask((width, height), blur_polygons)) > 0
        self.fill_mask = np.array(_polygon_mask((width, height), filled_polygons)) > 0
        self.blur_box = self._bounding_box(self.blur_mask)
        self.has_blur = self.blur_box is not None
        self.has_fill = bool(self.fill_mask.any())
        self.active = self.has_blur or self.has_fill

        # Maschere per i piani cromatici, sottocampionati di un fattore 2 e
        # impacchettati come in I420 (due righe di croma per riga di buffer).
        self._blur_chroma = self._chroma_mask(self.blur_mask)
        self._fill_chroma = self._chroma_mask(self.fill_mask)

        if self.active:
            self.logger.info(
                f"Frame privacy masks ready for {width}x{height}: "
                f"{len(blur_polygons)} blurred, {len(filled_polygons)} filled."
            )

    @staticmethod
    def _bounding_box(mask):
        """Riquadro che racchiude la maschera, o None se vuota."""
        if not mask.any():
            return None
        rows = np.where(np.any(mask, axis=1))[0]
        cols = np.where(np.any(mask, axis=0))[0]
        return int(cols[0]), int(rows[0]), int(cols[-1]) + 1, int(rows[-1]) + 1

    def _chroma_mask(self, mask):
        """Sottocampiona la maschera per i piani U/V nel layout impacchettato."""
        h, w = self.height, self.width
        if h % 4 or w % 2 or not mask.any():
            return None
        # OR sui blocchi 2x2: un pixel cromatico è coperto se lo è almeno
        # uno dei quattro pixel di luminanza corrispondenti.
        small = (mask[0::2, 0::2] | mask[1::2, 0::2] |
                 mask[0::2, 1::2] | mask[1::2, 1::2])
        return np.ascontiguousarray(small).reshape(h // 4, w)

    def _blur_region(self, region):
        h, w = region.shape[:2]
        small = cv2.resize(region, (max(1, w // self.factor), max(1, h // self.factor)),
                           interpolation=cv2.INTER_AREA)
        return cv2.resize(small, (w, h), interpolation=cv2.INTER_LINEAR)

    @staticmethod
    def _writable(frame):
        return frame if frame.flags.writeable else frame.copy()

    def apply_rgb(self, frame):
        """Applica le maschere a un frame a 3 canali (RGB o BGR), in place."""
        if not self.active:
            return frame
        try:
            frame = self._writable(frame)
            if self.has_blur:
                x0, y0, x1, y1 = self.blur_box
                region = frame[y0:y1, x0:x1]
                selection = self.blur_mask[y0:y1, x0:x1]
                region[selection] = self._blur_region(region)[selection]
            if self.has_fill:
                frame[self.fill_mask] = 0
        except Exception as e:
            self.logger.error(f"Failed to apply privacy masks to frame: {e}", exc_info=True)
        return frame

    def apply_yuv420(self, frame):
        """Applica le maschere a un frame YUV420 planare (h*3/2, w), in place."""
        if not self.active:
            return frame
        try:
            frame = self._writable(frame)
            h, w = self.height, self.width
            luma = frame[:h]
            chroma_planes = (frame[h:h + h // 4], frame[h + h // 4:h + h // 2])

            if self.has_blur:
                x0, y0, x1, y1 = self.blur_box
                region = luma[y0:y1, x0:x1]
                selection = self.blur_mask[y0:y1, x0:x1]
                region[selection] = self._blur_region(region)[selection]
                # Sui piani cromatici, a metà risoluzione, si appiattisce il
                # colore sulla media della regione: sfocarli separatamente
                # costerebbe di più senza aggiungere nulla di riconoscibile.
                if self._blur_chroma is not None:
                    for plane in chroma_planes:
                        plane[self._blur_chroma] = int(plane[self._blur_chroma].mean())

            if self.has_fill:
                luma[self.fill_mask] = 0
                if self._fill_chroma is not None:
                    for plane in chroma_planes:
                        plane[self._fill_chroma] = 128  # croma neutro: nero pieno
        except Exception as e:
            self.logger.error(f"Failed to apply privacy masks to frame: {e}", exc_info=True)
        return frame