#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
sys.excepthook = sys.__excepthook__

import time
import os
from PIL import Image, ImageDraw, ImageFont, ImageStat
import io
from io import BytesIO
from fractions import Fraction
from lib.helpers import (
    logRecursive,
    load_privacy_rois,
    remap_rois_to_view,
    centered_view,
    FramePrivacyMasker,
)
from lib import assets, paths, stream_overlay
import random
import threading
import subprocess
import threading
import select
import cv2
import numpy as np
import importlib.metadata
from libcamera import Transform
import copy
import json


# Voce "Manuale" del menu AWB: non e' una modalita' di libcamera, e' il modo
# di dire "spegni l'automatismo e usa i guadagni indicati".
AWB_MANUAL = 7


def cameraFactory(camera_type, *args, **kwargs):
    if camera_type == 'fakeCamera':
        return fakeCameraDevice(*args, **kwargs)
    elif camera_type == 'piCamera':
        return PiCameraDevice(*args, **kwargs)
    else:
        raise ValueError(f"Unknown camera type: {camera_type}")

class fakeCameraDevice:
    def __init__(self, params, streamParams, onvifParams, deviceParams, logger,
                 annotation=None, overlayImages=None):
        self.logger = logger
        self.params = params
        self.streamParams = streamParams
        self.onvifParams = onvifParams
        self.annotation = annotation or {}
        self.overlayImages = overlayImages or []
        self.logger.info("Camera Object Created")

    def update_config(self, new_params, new_stream_params, new_device_params,
                      new_annotation=None, new_overlay_images=None):
        self.logger.info("Updating camera configuration with new settings...")
        self.params = new_params
        self.streamParams = new_stream_params
        self.deviceParams = new_device_params
        self.annotation = new_annotation or {}
        self.overlayImages = new_overlay_images or []

    def fakeImage(self):
        width = 4000
        height = 3000
        text = "This is a test image"
        # Create a blank image with a background color
        color = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
        image = Image.new("RGB", (width, height), color)
        return image

    def takePicture(self, dayperiod):
        self.logger.info(f"Starting capture - {dayperiod}")
        image = self.fakeImage()
        # Save the image to a byte buffer
        image_buffer = BytesIO()
        image.save(image_buffer, format='JPEG')
        image_buffer.seek(0)
        return image_buffer, {}
    
    def streamStart(self, dayperiod):
        self.logger.info("Fake streaming started.")

    def streamStop(self):
        self.logger.info("Fake streaming stopped.")

    def get_image(self):
        self.logger.info("Getting fake image.")
        return self.takePicture('day')

class PiCameraDevice:
    def __init__(self, params, streamParams, onvifParams, deviceParams, logger,
                 annotation=None, overlayImages=None):
        self.logger = logger
        self.params = params
        self.streamParams = streamParams
        self.onvifParams = onvifParams
        self.deviceParams = deviceParams
        # Servono solo allo streaming: la foto viene annotata a valle, da
        # ImageAnnotator e ImageOverlay.
        self.annotation = annotation or {}
        self.overlayImages = overlayImages or []
        self.last_known_exposure_index = None
        self.capture_info = None
        self.camera_lock = threading.Lock()
        self.logger.info("Camera Object Created")
        self._load_capture_indices()
        from picamera2 import Picamera2
        try:
            version = importlib.metadata.version('picamera2')
            self.logger.info(f"Using picamera2 version: {version}")
        except importlib.metadata.PackageNotFoundError:
            self.logger.warning("Could not determine picamera2 version.")
        self.camera = Picamera2()
        self.running = False
        # Define and create the shared memory directory for stream frames
        self.shmem_path = paths.SHMEM_DIR
        os.makedirs(self.shmem_path, exist_ok=True)
        self.logger.info(f"Shared memory path for stream frames set to: {self.shmem_path}")

    def _load_capture_indices(self):
        """
        Carica gli ultimi indici noti per esposizione e gain dal file.
        Gestisce l'assenza del file o un formato obsoleto.
        """
        try:
            with open(paths.CAPTURE_INFO_FILE, 'r') as f:
                data = json.load(f)
                self.last_known_exposure_index = data.get('exposure_index', 8)
                self.last_known_gain_index = data.get('gain_index', 0)
                self.logger.info(
                    f"Caricati indici: Esposizione={self.last_known_exposure_index}, "
                    f"Gain={self.last_known_gain_index}"
                )
        except (FileNotFoundError, json.JSONDecodeError):
            self.logger.warning(
                "File .capture_info non trovato o illeggibile. "
                "Uso indici di default (Esposizione=8, Gain=0)."
            )
            self.last_known_exposure_index = 8
            self.last_known_gain_index = 0

    def _store_capture_indices(self):
        """
        Salva gli indici correnti di esposizione e gain su file.
        """
        data_to_store = {
            'exposure_index': self.last_known_exposure_index,
            'gain_index': self.last_known_gain_index
        }
        try:
            with open(paths.CAPTURE_INFO_FILE, 'w') as f:
                json.dump(data_to_store, f, indent=4)
                self.logger.info(
                    f"Salvati nuovi indici: Esposizione={data_to_store['exposure_index']}, "
                    f"Gain={data_to_store['gain_index']}"
                )
        except Exception as e:
            self.logger.error(f"Impossibile salvare il file .capture_info: {e}")


    def update_config(self, new_params, new_stream_params, new_device_params,
                      new_annotation=None, new_overlay_images=None):
        with self.camera_lock:
            self.logger.info("Updating camera configuration with new settings...")
            self.params = new_params
            self.streamParams = new_stream_params
            self.deviceParams = new_device_params
            self.annotation = new_annotation or {}
            self.overlayImages = new_overlay_images or []

    def get_image(self ):
        with self.camera_lock:
            output_buffer = BytesIO()
            self.logger.debug("Getting Image")
            self.camera.capture_file(output_buffer, format="jpeg")
            metadata = self.camera.capture_metadata()
            self.logger.debug(metadata)
            return output_buffer, metadata

    def _apply_white_balance(self, controls, params):
        """
        Bilanciamento del bianco per lo scatto: automatico o a guadagni fissi.

        Con la modalità "Manuale" l'automatismo viene spento e restano i
        guadagni di rosso e blu indicati: è il rimedio alle luci al sodio, che
        l'AWB insegue virando l'intera immagine. Con qualunque altra modalità
        i guadagni sono ignorati.
        """
        try:
            mode = int(params.get("AwbMode", 0))
        except (TypeError, ValueError):
            mode = 0

        if mode == AWB_MANUAL:
            try:
                red = float(params.get("ColourGainRed", 0) or 0)
                blue = float(params.get("ColourGainBlue", 0) or 0)
            except (TypeError, ValueError):
                red = blue = 0.0

            if red > 0 and blue > 0:
                controls["AwbEnable"] = False
                controls["ColourGains"] = (red, blue)
                controls.pop("AwbMode", None)
                self.logger.info(f"Bilanciamento del bianco manuale: guadagni R={red:.2f}, B={blue:.2f}")
                return controls

            # Manuale senza guadagni validi non e' una richiesta eseguibile:
            # meglio l'automatico che una foto con i colori a caso.
            self.logger.warning(
                "Bilanciamento manuale richiesto ma i guadagni non sono validi: torno all'automatico."
            )
            mode = 0

        controls["AwbEnable"] = True
        controls["AwbMode"] = mode
        controls.pop("ColourGains", None)
        self.logger.info(f"Bilanciamento del bianco automatico, modalità {mode}")
        return controls

    def takePicture(self, dayperiod):
        """
        Cattura un'immagine usando l'esposizione automatica per 'day'
        o un bracketing manuale su esposizione E guadagno per le altre fasi.
        """
        with self.camera_lock:
            self.logger.info(f"--- Inizio cattura per '{dayperiod}' ---")
            # Nelle fasi scure il bracketing puo' durare minuti: i tempi finiscono
            # nel log a ogni passo, cosi' si vede che la cattura sta lavorando.
            capture_started = time.monotonic()
            params = copy.deepcopy(self.params.get(dayperiod, {}))
            
            # Costanti per il bracketing
            SHUTTER_SPEEDS_SECONDS = [1/8, 1/4, 1/2, 3/4, 1, 2, 4, 6, 8, 10, 12, 15, 20, 30, 45]
            ANALOG_GAINS = [1.0, 2.0, 4.0, 8.0]
            
            BRIGHTNESS_TARGET_MIN = params.get("MinTargetBrightness", 40)
            BRIGHTNESS_TARGET_MAX = params.get("MaxTargetBrightness", 55)

            try:
                transform = Transform(hflip=self.deviceParams.get("hflip", False), vflip=self.deviceParams.get("vflip", False))
                config = self.camera.create_still_configuration(transform=transform, buffer_count=3, queue=False)
                self.camera.configure(config)

                if dayperiod == "day":
                    # --- LOGICA PER SCATTO DIURNO (INVARIATA) ---
                    self.logger.info("Modalità diurna: uso l'esposizione automatica (AeEnable=True).")
                    day_params = {
                        "AeEnable": True,
                        "AeMeteringMode": params.get("AeMeteringMode", 0),
                        "AnalogueGain": 1.0, "ExposureTime": 0, "ExposureValue": 0,
                        "HdrMode": params.get("HdrMode", 2), "NoiseReductionMode": params.get("NoiseReductionMode", 1),
                        "Sharpness": params.get("Sharpness", 4)
                    }
                    self._apply_white_balance(day_params, params)
                    self.camera.set_controls(day_params)
                    self.camera.start()
                    self.logger.info("Attesa stabilizzazione esposizione automatica (2 secondi)...")
                    time.sleep(2)
                    output_buffer = io.BytesIO()
                    self.camera.capture_file(output_buffer, format="jpeg")
                    metadata = self.camera.capture_metadata()
                    self.logger.info(
                        f"Cattura diurna completata in {time.monotonic() - capture_started:.1f}s. "
                        f"Gain: {metadata.get('AnalogueGain'):.2f}, "
                        f"Esposizione: {metadata.get('ExposureTime')/1000000:.4f}s"
                    )
                    return output_buffer, metadata

                else:
                    # --- LOGICA PER SCATTI NOTTURNI/CREPUSCOLO (CON AGGIUNTA DEL GAIN) ---
                    self.logger.info(
                        "Modalità crepuscolo/notte: bracketing manuale su Esposizione e Gain. "
                        "Ogni tentativo costa 2s di stabilizzazione più il tempo di posa, "
                        "quindi la cattura può richiedere minuti."
                    )
                    shutter_speeds_us = [int(s * 1_000_000) for s in SHUTTER_SPEEDS_SECONDS]
                    
                    # Carica l'ultimo stato noto per esposizione E gain
                    self._load_capture_indices()
                    shutter_idx = getattr(self, 'last_known_exposure_index', 8)
                    gain_idx = getattr(self, 'last_known_gain_index', 0)

                    manual_controls = {
                        "AeEnable": False,
                        "FrameDurationLimits": (100, 100_000_000),
                        "NoiseReductionMode": params.get("NoiseReductionMode", 1)
                    }
                    self._apply_white_balance(manual_controls, params)
                    self.camera.set_controls(manual_controls)
                    
                    exp_results = {}
                    max_attempts = 40 # Aumentato per coprire più combinazioni

                    for attempt in range(max_attempts):
                        # Validazione indici correnti
                        shutter_idx = max(0, min(shutter_idx, len(shutter_speeds_us) - 1))
                        gain_idx = max(0, min(gain_idx, len(ANALOG_GAINS) - 1))
                        
                        current_state = (shutter_idx, gain_idx)

                        # --- ANTI-BOUNCING (ora basato su stato combinato) ---
                        if current_state in exp_results:
                            self.logger.warning(f"Rilevata oscillazione! Stato (shutter_idx={shutter_idx}, gain_idx={gain_idx}) già testato. Scelgo il migliore.")
                            break

                        exposure_us = shutter_speeds_us[shutter_idx]
                        gain = ANALOG_GAINS[gain_idx]
                        
                        attempt_started = time.monotonic()
                        self.logger.info(
                            f"[{attempt_started - capture_started:.0f}s] Tentativo {attempt + 1}/{max_attempts}: "
                            f"Idx Esp={shutter_idx}, Idx Gain={gain_idx} "
                            f"({exposure_us/1_000_000:.3f}s, Gain={gain:.1f}x)"
                        )
                        self.camera.set_controls({"ExposureTime": exposure_us, "AnalogueGain": gain})
                        
                        self.camera.start()
                        time.sleep(2) # Warmup sensore
                        
                        current_buffer = io.BytesIO()
                        self.camera.capture_file(current_buffer, format="jpeg")
                        metadata = self.camera.capture_metadata()
                        self.camera.stop()

                        if not current_buffer.getbuffer().nbytes:
                            self.logger.error("Buffer immagine vuoto, salto.")
                            continue

                        current_buffer.seek(0)
                        with Image.open(current_buffer) as img:
                            brightness = ImageStat.Stat(img.convert('L')).mean[0]

                        self.logger.info(
                            f"Tentativo {attempt + 1} concluso in {time.monotonic() - attempt_started:.1f}s, "
                            f"luminosità misurata: {brightness:.2f} "
                            f"(obiettivo {BRIGHTNESS_TARGET_MIN}-{BRIGHTNESS_TARGET_MAX})"
                        )
                        
                        exp_results[current_state] = {"brightness": brightness, "metadata": metadata, "image": current_buffer}

                        if BRIGHTNESS_TARGET_MIN <= brightness <= BRIGHTNESS_TARGET_MAX:
                            self.logger.info(
                                f"Esposizione ottimale trovata in {time.monotonic() - capture_started:.1f}s "
                                f"con {attempt + 1} tentativi. "
                                f"Salvo lo stato (shutter_idx={shutter_idx}, gain_idx={gain_idx})."
                            )
                            self.last_known_exposure_index = shutter_idx
                            self.last_known_gain_index = gain_idx
                            self._store_capture_indices()
                            return current_buffer, metadata
                        
                        # --- LOGICA DI AGGIORNAMENTO INDICI ---
                        if brightness < BRIGHTNESS_TARGET_MIN:
                            # Immagine troppo scura: aumenta l'esposizione
                            if shutter_idx < len(shutter_speeds_us) - 1:
                                shutter_idx += 1 # Priorità: aumentare il tempo di posa
                            elif gain_idx < len(ANALOG_GAINS) - 1:
                                gain_idx += 1 # Solo se il tempo è al massimo, aumenta il gain
                            else:
                                self.logger.warning("Raggiunto limite massimo di esposizione e gain. Interrompo ricerca.")
                                break
                        elif brightness > BRIGHTNESS_TARGET_MAX:
                            # Immagine troppo chiara: diminuisci l'esposizione
                            if gain_idx > 0:
                                gain_idx -= 1 # Priorità: diminuire il gain
                            elif shutter_idx > 0:
                                shutter_idx -= 1 # Solo se il gain è al minimo, diminuisci il tempo
                            else:
                                self.logger.warning("Raggiunto limite minimo di esposizione e gain. Interrompo ricerca.")
                                break

                    # --- LOGICA DI FALLBACK (se non si trova l'esposizione perfetta) ---
                    self.logger.warning("Nessuna esposizione perfetta trovata. Scelgo la più vicina.")
                    if not exp_results: return None, {}
                    target_br = (BRIGHTNESS_TARGET_MIN + BRIGHTNESS_TARGET_MAX) / 2
                    
                    # La chiave di ricerca ora è una tupla (shutter_idx, gain_idx)
                    best_state = min(exp_results.keys(), key=lambda state: abs(exp_results[state]['brightness'] - target_br))
                    best_result = exp_results[best_state]
                    
                    self.logger.info(
                        f"Scatto migliore dopo {time.monotonic() - capture_started:.1f}s e {len(exp_results)} tentativi: "
                        f"Idx Esp={best_state[0]}, Idx Gain={best_state[1]}, "
                        f"Luminosità={best_result['brightness']:.2f}"
                    )
                    self.last_known_exposure_index = best_state[0]
                    self.last_known_gain_index = best_state[1]
                    self._store_capture_indices() # Salva lo stato migliore trovato
                    return best_result['image'], best_result['metadata']

            except Exception as e:
                self.logger.error(f"Errore durante takePicture: {e}", exc_info=True)
                if self.camera.started: self.camera.stop()
                return None, {}
            finally:
                if self.camera.started:
                    self.camera.stop()
                    self.logger.info("--- Fine cattura, camera fermata. ---")
                    time.sleep(2)

    def takePicture_old(self, dayperiod):
        """
        Cattura un'immagine, con l'opzione di lasciare la camera in esecuzione.
        """
        with self.camera_lock:
            self.logger.info(f"--- Inizio cattura per '{dayperiod}' ---")
            output_buffer = BytesIO()
            
            try:
                # 1. Prepara i parametri e i controlli
                params = copy.deepcopy(self.params.get(dayperiod, {}))
                is_auto_mode = params.get("AeEnable", True)

                # Prepara la configurazione base della camera
                transform = Transform(hflip=self.deviceParams.get("hflip", False), vflip=self.deviceParams.get("vflip", False))
                config = self.camera.create_still_configuration(transform=transform)
                self.camera.configure(config)

                params['AwbEnable'] = True
                params['AeExposureMode'] = 2 # prefer long exposure
                self.camera.set_controls(params)

                self.camera.start()
                self.logger.info("In attesa della stabilizzazione del sensore (2 secondi)...")
                time.sleep(2)

                self.logger.info(f"Cattura dell'immagine {params['ExposureTime']/1000000:.2f}s a Gain {params.get('AnalogueGain')}")
                self.camera.capture_file(output_buffer, format="jpeg")
                metadata = self.camera.capture_metadata()
                self.logger.info(f"Cattura completata. Gain: {metadata.get('AnalogueGain'):.2f}, Esposizione: {metadata.get('ExposureTime')/1000000:.2f}")

                return output_buffer, metadata

            except Exception as e:
                self.logger.error(f"Errore durante takePicture per '{dayperiod}': {e}", exc_info=True)
                if self.camera.started:
                        self.camera.stop()
                return None, {}
            finally:
                if self.camera.started:
                    self.camera.stop()
                    self.logger.info("--- Fine cattura, camera fermata. ---")


    def _stream_audio_input(self):
        """
        Ingresso audio di ffmpeg: il brano configurato oppure il silenzio.

        Resta sempre l'ingresso numero 1, perché è quello che le uscite
        mappano con '-map 1:a' e i loghi contano a partire dal 2. Il brano
        va in loop infinito e viene letto a velocità reale: senza '-re'
        ffmpeg lo divorerebbe alla massima velocità, mandando l'audio
        avanti al video di ore.
        """
        source = self.streamParams.get("audio_file", "") or ""
        track = assets.path(source)
        if source and not track:
            self.logger.warning(
                f"Audio dello streaming '{source}' non trovato fra gli assets: vado in silenzio."
            )
        if not track:
            return ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"], []

        try:
            volume = max(0, min(100, int(self.streamParams.get("audio_volume", 100))))
        except (TypeError, ValueError):
            volume = 100

        self.logger.info(f"Audio dello streaming: {os.path.basename(track)} al {volume}% di volume.")
        filters = [] if volume == 100 else ["-af", f"volume={volume / 100:.2f}"]
        return ["-stream_loop", "-1", "-re", "-i", track], filters

    def _stream_outputs(self, primary_url, video_label="0:v"):
        """
        Argomenti di uscita per ffmpeg: una o più destinazioni RTMP.

        Con più destinazioni si usa il muxer 'tee', che duplica il flusso già
        codificato senza rifare l'encoding. 'onfail=ignore' fa sì che una
        destinazione irraggiungibile non trascini giù le altre.

        Il video da mappare è l'ingresso grezzo oppure l'uscita del
        filtergraph che disegna annotazione e loghi.
        """
        extra = [url.strip() for url in self.streamParams.get("extra_destinations", []) or [] if url.strip()]
        if not extra:
            return ["-map", video_label, "-map", "1:a", "-f", "flv", primary_url]

        destinations = "|".join(f"[f=flv:onfail=ignore]{url}" for url in [primary_url] + extra)
        # Solo gli host: l'ultimo segmento dell'URL è la stream key e non
        # deve finire nel log.
        hosts = [url.split("/")[2] if "//" in url else "?" for url in [primary_url] + extra]
        self.logger.info(f"Restreaming to {len(extra) + 1} destinations: {', '.join(hosts)}")
        # global_header è raccomandato dalla documentazione di 'tee' quando i
        # formati di uscita richiedono header globali, come flv con H.264/AAC:
        # senza, le uscite oltre la prima possono risultare malformate.
        return [
            "-flags", "+global_header",
            "-map", video_label, "-map", "1:a",
            "-f", "tee", destinations,
        ]

    def _still_width(self):
        """
        Larghezza in pixel della foto, ritaglio compreso.

        È il riferimento delle coordinate di annotazione e loghi, che sullo
        streaming vanno riscalate.
        """
        crop = self.params.get("crop", {})
        if crop.get("enabled", False) and crop.get("width"):
            return int(crop["width"])
        return int(self.camera.create_still_configuration()["main"]["size"][0])

    def _still_sensor_view(self):
        """
        Porzione di sensore coperta dalla foto, in coordinate del sensore.

        È la vista su cui l'utente disegna le privacy mask, quindi tiene
        conto anche dell'eventuale ritaglio applicato da ImageCropper.
        """
        try:
            pixel_w, pixel_h = self.camera.camera_properties["PixelArraySize"]
            full_view = (0.0, 0.0, float(pixel_w), float(pixel_h))

            crop = self.params.get("crop", {})
            if not crop.get("enabled", False):
                return full_view

            still_w, still_h = self.camera.create_still_configuration()["main"]["size"]
            # Stesso riquadro calcolato da ImageCropper.crop()
            left = max(0, (still_w - crop["width"]) / 2 + crop["x_offset"])
            top = max(0, (still_h - crop["height"]) / 2 + crop["y_offset"])
            right = min(still_w, (still_w + crop["width"]) / 2 + crop["x_offset"])
            bottom = min(still_h, (still_h + crop["height"]) / 2 + crop["y_offset"])

            return (
                left / still_w * pixel_w,
                top / still_h * pixel_h,
                (right - left) / still_w * pixel_w,
                (bottom - top) / still_h * pixel_h,
            )
        except Exception as e:
            self.logger.error(f"Could not determine the still sensor view: {e}")
            return None

    def _stream_sensor_view(self, fallback_view, aspect):
        """
        Porzione di sensore coperta dallo streaming, letta da ScalerCrop.

        La camera va già avviata nella configurazione video. Se il dato non
        è disponibile si ripiega sul ritaglio centrato del formato richiesto,
        che è il comportamento predefinito di libcamera.
        """
        try:
            crop = self.camera.capture_metadata().get("ScalerCrop")
            if crop and len(crop) == 4 and crop[2] and crop[3]:
                self.logger.info(f"Stream ScalerCrop reported by the camera: {tuple(crop)}")
                return tuple(float(v) for v in crop)
            self.logger.warning("ScalerCrop not reported by the camera.")
        except Exception as e:
            self.logger.error(f"Could not read ScalerCrop: {e}")

        if not fallback_view:
            return None
        view = centered_view(fallback_view, aspect)
        self.logger.warning(f"Falling back to a centred {aspect:.3f} crop for the stream view: {view}")
        return view

    def streamStart(self, dayperiod):
        if self.running:
            self.logger.warning("Stream is already running. Please stop it first.")
            return
        self.logger.info("Starting video streaming thread")
        self.streamThread = threading.Thread(target=self.streamNow, args=(dayperiod,), daemon=True, name="YouTubeStreamThread")
        self.streamThread.start()

    def streamNow(self, dayperiod):
        with self.camera_lock:
            # --- 1. CONTROLLO ABILITAZIONE STREAM ---
            # Controlla se gli stream sono abilitati nella configurazione.
            # Il metodo .get() ritorna False se la chiave non è presente.
            dayperiod_params = copy.deepcopy(self.streamParams.get(dayperiod, {}))
            yt_enabled = self.streamParams.get("enabled", False)
            onvif_enabled = self.onvifParams.get("enabled", False)
            
            self.logger.info(f"Stream status: YouTube={'ENABLED' if yt_enabled else 'DISABLED'}, ONVIF={'ENABLED' if onvif_enabled else 'DISABLED'}")

            # Se nessuno stream è abilitato, esci subito.
            if not yt_enabled and not onvif_enabled:
                self.logger.warning("Both YouTube and ONVIF streams are disabled. Exiting.")
                self.running = False # Assicura che lo stato sia consistente
                return

            # --- 2. CONFIGURAZIONE CAMERA (COMUNE A ENTRAMBI) ---
            # Questa configurazione è necessaria se almeno uno stream è attivo.
            fr = dayperiod_params.pop("framerate", 10)
            w, h = self.streamParams["width"], self.streamParams["height"]
            onvif_w = self.onvifParams.get("onvif_w", 1920)
            onvif_h = int(onvif_w * (h / w))
            
            hflip = self.deviceParams.get("hflip", False)
            vflip = self.deviceParams.get("vflip", False)
            transform = Transform(hflip=hflip, vflip=vflip)

            video_config = self.camera.create_video_configuration(
                main={"size": (w, h), "format": "YUV420"},
                lores={"size": (onvif_w, onvif_h), "format": "RGB888"},
                controls={"FrameRate": fr, "HdrMode": 0},
                transform=transform,
                buffer_count=6
            )
            self.camera.configure(video_config)
            # AwbMode e guadagni non vanno passati grezzi: la voce "Manuale"
            # non esiste per libcamera e i guadagni sono chiavi nostre.
            awb_params = {
                key: dayperiod_params.pop(key)
                for key in ("AwbMode", "ColourGainRed", "ColourGainBlue")
                if key in dayperiod_params
            }
            dayperiod_params["AeEnable"] = True
            self._apply_white_balance(dayperiod_params, awb_params)
            self.logger.info(f"dayperiod_params: {dayperiod_params}")
            self.camera.set_controls(dayperiod_params)
            self.camera.start()
            time.sleep(2)

        # --- 3. INIZIALIZZAZIONE CONDIZIONALE ---
        self.ffmpeg_proc = None
        output_image_path = None

        # Le privacy mask vengono rasterizzate qui, una volta per avvio dello
        # streaming: le modifiche fatte dall'interfaccia web entrano in vigore
        # al ciclo di cattura successivo, quando lo stream viene riavviato.
        # Sono disegnate sulla foto, che ha un formato diverso dallo stream:
        # vanno riportate sulla porzione di sensore che lo stream inquadra.
        rois = load_privacy_rois(self.logger)
        if rois:
            still_view = self._still_sensor_view()
            stream_view = self._stream_sensor_view(still_view, w / h)
            self.logger.info(f"Sensor view - still: {still_view}, stream: {stream_view}")
            rois = remap_rois_to_view(rois, still_view, stream_view, self.logger)
        yt_masker = FramePrivacyMasker(rois, w, h, logger=self.logger) if yt_enabled else None
        # Il flusso lores serve a ONVIF e all'anteprima della pagina Cam
        # Control, quindi viene mascherato ogni volta che si trasmette.
        lores_masker = FramePrivacyMasker(rois, onvif_w, onvif_h, logger=self.logger)

        if yt_enabled:
            api_key = self.streamParams["yt_api_key"]
            bitrate = self.streamParams.get("bitrate", "4500k")
            bufsize = self.streamParams.get("bufsize", "9000k")

            # Annotazione e loghi li disegna ffmpeg prima di codificare: sui
            # frame YUV420 grezzi costerebbe molto di più.
            overlay_inputs, overlay_filter, video_label = ([], None, "0:v")
            if self.streamParams.get("overlay", False):
                overlay_inputs, overlay_filter, video_label = stream_overlay.build(
                    self.annotation, self.overlayImages, (w, h), self._still_width(),
                    self.shmem_path, self.logger,
                )

            audio_input, audio_filters = self._stream_audio_input()

            ffmpeg_cmd = [
                "ffmpeg", "-f", "rawvideo", "-pix_fmt", "yuv420p", "-s", f"{w}x{h}", "-r", str(fr), "-i", "-",
            ] + audio_input + overlay_inputs + (["-filter_complex", overlay_filter] if overlay_filter else []) + [
                "-c:v", "libx264", "-preset", "veryfast", "-b:v", bitrate, "-maxrate", bitrate, "-bufsize", bufsize,
                "-g", str(int(fr * 2)),
                "-c:a", "aac", "-ar", "44100", "-b:a", "128k",
            ] + audio_filters + self._stream_outputs(f"rtmp://a.rtmp.youtube.com/live2/{api_key}", video_label)

            self.logger.info("Starting ffmpeg process for YouTube stream...")
            self.ffmpeg_proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE)

        # Un fotogramma al secondo su tmpfs: lo consuma ONVIF e lo mostra
        # l'anteprima in diretta della pagina Cam Control.
        os.makedirs(self.shmem_path, exist_ok=True)
        output_image_path = paths.STREAM_PREVIEW
        self.logger.info(f"Stream frame saving enabled. Path: {output_image_path}")

        # --- 4. LOOP PRINCIPALE DELLO STREAMING ---
        self.running = True
        last_frame_save_time = 0

        while self.running:
            request = None
            try:
                request = self.camera.capture_request()

                # --- Gestione Stream YouTube ---
                if yt_enabled and self.ffmpeg_proc and self.ffmpeg_proc.stdin:
                    main_frame = request.make_array("main")
                    if yt_masker.active:
                        main_frame = yt_masker.apply_yuv420(main_frame)
                    if select.select([], [self.ffmpeg_proc.stdin], [], 0)[1]:
                        try:
                            self.ffmpeg_proc.stdin.write(main_frame.tobytes())
                            self.ffmpeg_proc.stdin.flush()
                        except (BrokenPipeError, OSError):
                            self.logger.error("Broken pipe with ffmpeg, stopping stream.")
                            break # Esce dal loop se ffmpeg si chiude inaspettatamente
                    else:
                        self.logger.warning("Frame skipped for YouTube (ffmpeg busy)")
                
                # --- Fotogramma condiviso (ONVIF e anteprima web) ---
                current_time = time.time()
                if current_time - last_frame_save_time >= 1.0: # Salva al massimo un frame al secondo
                    lores_frame = request.make_array("lores")
                    if lores_masker.active:
                        lores_frame = lores_masker.apply_rgb(lores_frame)
                    try:
                        rgb_frame = cv2.cvtColor(lores_frame, cv2.COLOR_BGR2RGB)
                        img = Image.fromarray(rgb_frame, 'RGB')
                        img.save(output_image_path, 'JPEG', quality=85)
                        last_frame_save_time = current_time
                        self.logger.debug(f"Saved stream frame to {output_image_path}")
                    except Exception as e:
                        self.logger.error(f"Failed to save stream frame: {e}")

            except Exception as e:
                self.logger.error(f"Streaming Error: {e}", exc_info=True)
                break
            finally:
                if request:
                    request.release()
        self.logger.info("Streaming loop requested to stop. Cleaning up resources...")
        
        if yt_enabled and hasattr(self, 'ffmpeg_proc') and self.ffmpeg_proc and self.ffmpeg_proc.poll() is None:
            self.logger.info("Attempting graceful shutdown of ffmpeg process...")
            try:
                if self.ffmpeg_proc.stdin:
                    self.ffmpeg_proc.stdin.close()
                self.ffmpeg_proc.wait(timeout=2)
                self.logger.info("ffmpeg process exited gracefully.")
            except subprocess.TimeoutExpired:
                self.logger.warning("ffmpeg did not exit gracefully. Terminating...")
                self.ffmpeg_proc.terminate()
                try:
                    self.ffmpeg_proc.wait(timeout=2)
                    self.logger.info("ffmpeg process terminated successfully.")
                except subprocess.TimeoutExpired:
                    self.logger.error("ffmpeg did not terminate. Killing process...")
                    self.ffmpeg_proc.kill()
                    self.logger.info("ffmpeg process killed.")
            except (BrokenPipeError, OSError) as e:
                self.logger.error(f"Error while closing ffmpeg stdin: {e}. Terminating process.")
                self.ffmpeg_proc.terminate()
                time.sleep(1)
                if self.ffmpeg_proc.poll() is None:
                    self.ffmpeg_proc.kill()
        
        self.logger.info("Cleanup complete. Exiting streaming thread.")

    def streamStop(self):
        if not self.running:
            self.logger.info("Stream is not running.")
            return
            
        self.logger.info("Stopping video streaming...")
        self.running = False # This flag will cause the streamNow loop to exit

        if hasattr(self, "streamThread") and self.streamThread.is_alive():
            self.logger.info("Waiting for streaming thread to finish cleanup...")
            # REMOVED TIMEOUT: This will now block until the thread is actually finished.
            self.streamThread.join()
            self.logger.info("Streaming thread has finished.")

        if self.camera.started:
            self.logger.info("Stopping camera...")
            self.camera.stop()

        self.logger.info("✅ Streaming stopped correctly.")


if __name__ == '__main__':
    print("Devices Classes")

