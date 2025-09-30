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
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import json

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
        logRecursive(self.logger, self.ftp_host)

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

class ImageOverlay:
    def __init__(self, OverlayImages, logger):
        self.logger = logger
        self.OverlayImages = OverlayImages
        self.logger.info("ImageOverlay object created")
        logRecursive(self.logger, self.OverlayImages)
        self.downloadImages()

    def downloadImages(self):
        self.logger.info("Downloading overlay images")
        for OverlayImage in self.OverlayImages:
            if not OverlayImage["enabled"]:
                continue
            try:
                fd = urllib.request.urlopen(OverlayImage["url"])
                OlImg = io.BytesIO(fd.read())
                OverlayImage["image"] = Image.open(OlImg)
                self.logger.info(f"Downloaded {OverlayImage['name']}")
            except Exception as e:
                self.logger.error(f"Failed to download {OverlayImage['name']} from {OverlayImage['url']}: {e}")
        
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
                olImg = OverlayImage["image"]
                width, height = olImg.size
                width = width * int(OverlayImage["scale"])/100
                height = height * int(OverlayImage["scale"])/100
                olImg.thumbnail((width, height), Image.LANCZOS)
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
        logRecursive(self.logger, self.crop_settings)

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
        self.annotation = annotation
        self.content = self.annotation['Content']
        self.container = self.annotation['Container']

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
        self.latitude = latitude
        self.longitude = longitude
        self.elevation = elevation
        self.sun_rise_offset = sun_rise_offset
        self.sun_set_offset = sun_set_offset
        self.dusk_offset = dusk_offset
        self.dawn_offset = dawn_offset
        self.tz_info = tzlocal.get_localzone()
        self.logger = logger

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
    image.save("latest.jpg", format="JPEG")

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


class PrivacyMasker:
    """
    Applies privacy masks to an image by blurring polygonal regions
    defined in a JSON file.
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
        """
        Loads the ROI polygons from the .privacy_mask.json file.
        Returns an empty list if the file is not found or is invalid.
        """
        try:
            with open('.privacy_mask.json', 'r') as f:
                rois = json.load(f)
                self.logger.info(f"Loaded {len(rois)} privacy mask(s) from .privacy_mask.json.")
                return rois
        except FileNotFoundError:
            self.logger.info(".privacy_mask.json not found. No privacy masks will be applied.")
            return []
        except json.JSONDecodeError:
            self.logger.error(".privacy_mask.json is corrupted. Could not load privacy masks.")
            return []
        except Exception as e:
            self.logger.error(f"An unexpected error occurred while loading ROIs: {e}")
            return []

    def apply_masks(self, image_buffer):
        self.rois = self._load_rois()  # Reload ROIs in case the file has changed
        if not self.rois:
            return image_buffer

        try:
            self.logger.info("Applying privacy masks to image...")
            original_image = Image.open(image_buffer)
            
            # Ottieni le dimensioni dell'immagine che stai processando
            img_width, img_height = original_image.size

            blurred_image = original_image.filter(ImageFilter.GaussianBlur(radius=self.blur_radius))
            mask = Image.new('L', original_image.size, 0)
            mask_draw = ImageDraw.Draw(mask)

            for roi in self.rois:
                points = roi.get('points')
                if not points or len(points) < 3:
                    continue
                
                # --- MODIFICA CHIAVE: Converti i punti da % a pixel ---
                point_tuples = [
                    (
                        (p['x'] / 100.0) * img_width, 
                        (p['y'] / 100.0) * img_height
                    ) 
                    for p in points
                ]
                # --------------------------------------------------
                
                mask_draw.polygon(point_tuples, fill=255)

            original_image.paste(blurred_image, (0, 0), mask)

            out_buffer = io.BytesIO()
            original_image.save(out_buffer, format='JPEG')
            out_buffer.seek(0)
            
            self.logger.info("Privacy masks applied successfully.")
            return out_buffer
            
        except Exception as e:
            self.logger.error(f"Failed to apply privacy masks: {e}", exc_info=True)
            return image_buffer