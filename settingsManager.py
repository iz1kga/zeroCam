# -*- coding: utf-8 -*-
import os
import json
import logging
import threading
import time
import io
from datetime import datetime
from flask import Flask, Response, send_file, request, jsonify, render_template, redirect, url_for, flash
from waitress import serve
from PIL import Image, ImageDraw
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required

from lib import assets, config_backup, paths, tls
from lib.version import get_version
from lib.youtube_auth import YouTubeDeviceFlow

PRIVACY_MASK_PATH = paths.PRIVACY_MASK_FILE

# La classe User ora è disaccoppiata dall'oggetto zerocam globale.
class User(UserMixin):
    """Represents a user for the login system."""
    def __init__(self, user_id):
        self.id = user_id

    @staticmethod
    def get(user_id, security_config):
        """
        Gets a user object if the user_id exists in the configuration.
        `security_config` is passed in to avoid global dependencies.
        """
        expected_username = security_config.get('username', 'admin')
        if user_id == expected_username:
            return User(user_id)
        return None

class SettingsManager:
    """
    Manages the Flask web application for ZeroCam settings, stats, and controls.
    """
    def __init__(self, zerocam_instance):
        self.zerocam = zerocam_instance
        self.logger = self.zerocam.logger
        self.focus_aid_running = False
        self.youtube_device_flow = YouTubeDeviceFlow(self.logger)
        
        self.app = Flask(__name__, template_folder='templates', static_folder='static')
        # Il caricamento degli assets è l'unica richiesta con un corpo di
        # peso: il limite lo fa rifiutare a monte, senza scriverlo su disco.
        self.app.config['MAX_CONTENT_LENGTH'] = assets.MAX_SIZE
        # Il cookie di sessione non deve essere leggibile da JavaScript né
        # viaggiare verso altri siti. 'secure' si aggiunge solo quando
        # l'HTTP è spento, altrimenti impedirebbe di autenticarsi su di esso.
        self.app.config['SESSION_COOKIE_HTTPONLY'] = True
        self.app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
        self.logger.info("Initializing SettingsManager...")
        self._setup_secret_key()
        self.logger.info("Flask secret key is set.")
        self._setup_login_manager()
        self._register_routes()

        # Resa disponibile a tutti i template, header e pagina licenza inclusi
        version = get_version()
        self.app.context_processor(lambda: {'version': version})
        self.logger.info(f"Web interface serving zeroCAM version {version}")

    def _setup_secret_key(self):
        """Ensures a persistent Flask secret key is present in the configuration."""
        security_config = self.zerocam.config_manager.get_raw('security', {})
        if 'flask_secret_key' not in security_config or not security_config['flask_secret_key']:
            self.logger.warning("Flask secret key not found. Generating a new one.")
            secret_key = os.urandom(24).hex()
            
            # Lavora su una copia della configurazione per la modifica
            config_copy = json.loads(json.dumps(self.zerocam.config_manager.config))
            if 'security' not in config_copy:
                config_copy['security'] = {}
            config_copy['security']['flask_secret_key'] = secret_key
            self.zerocam.config_manager.save_config(config_copy)
        
        # Usa la chiave appena creata o quella esistente
        self.app.config['SECRET_KEY'] = self.zerocam.config_manager.get_raw('security')['flask_secret_key']

    def _setup_login_manager(self):
        """Initializes and configures the Flask-Login manager."""
        login_manager = LoginManager()
        login_manager.init_app(self.app)
        login_manager.login_view = 'login'

        @login_manager.user_loader
        def load_user(user_id):
            # Passa la configurazione di sicurezza in modo esplicito
            security_config = self.zerocam.config_manager.get_raw('security', {})
            return User.get(user_id, security_config)

    def _register_routes(self):
        """Adds all URL rules (routes) to the Flask application."""
        # Aggiunge le route associandole ai metodi di questa classe
        self.app.add_url_rule('/login', 'login', self.login, methods=['GET', 'POST'])
        self.app.add_url_rule('/logout', 'logout', self.logout, methods=['POST'])
        self.app.add_url_rule('/', 'index', self.index)
        self.app.add_url_rule('/latest.jpg', 'latest_image', self.latest_image)
        self.app.add_url_rule('/stream_latest.jpg', 'stream_latest_image', self.stream_latest_image)
        self.app.add_url_rule('/view/pages/<page_name>', 'serve_page_template', self.serve_page_template)
        
        # API Routes
        self.app.add_url_rule('/api/restart', 'restart', self.restart, methods=['POST'])
        self.app.add_url_rule('/api/change-password', 'change_password', self.change_password, methods=['POST'])
        self.app.add_url_rule('/api/config', 'handle_config', self.handle_config, methods=['GET', 'POST'])
        self.app.add_url_rule('/api/schema', 'get_schema', self.get_schema)
        self.app.add_url_rule('/api/config/backup', 'backup_config', self.backup_config, methods=['POST'])
        self.app.add_url_rule('/api/config/restore', 'restore_config', self.restore_config, methods=['POST'])
        self.app.add_url_rule('/api/log', 'get_log', self.get_log)
        self.app.add_url_rule('/api/stats', 'get_stats', self.get_stats)
        self.app.add_url_rule('/api/status/capture', 'get_capture_status', self.get_capture_status)
        self.app.add_url_rule('/api/status/stream', 'get_stream_status', self.get_stream_status)
        self.app.add_url_rule('/api/take_photo', 'take_photo', self.take_photo, methods=['POST'])
        self.app.add_url_rule('/api/timelapse', 'get_timelapse', self.get_timelapse, methods=['GET'])
        self.app.add_url_rule('/api/timelapse/run', 'run_timelapse', self.run_timelapse, methods=['POST'])
        self.app.add_url_rule('/api/youtube/device/start', 'youtube_device_start', self.youtube_device_start, methods=['POST'])
        self.app.add_url_rule('/api/youtube/device/poll', 'youtube_device_poll', self.youtube_device_poll, methods=['POST'])
        self.app.add_url_rule('/api/timelapse/frames', 'timelapse_frames', self.timelapse_frames, methods=['GET'])
        self.app.add_url_rule('/timelapse/frame/<name>', 'timelapse_frame', self.timelapse_frame)
        # Pagina pubblica: sono le uniche rotte senza autenticazione, e
        # rispondono solo se l'utente le ha abilitate.
        self.app.add_url_rule('/public', 'public_page', self.public_page, methods=['GET'])
        self.app.add_url_rule('/public/latest.jpg', 'public_image', self.public_image, methods=['GET'])
        self.app.add_url_rule('/public/info', 'public_info', self.public_info, methods=['GET'])
        self.app.add_url_rule('/api/assets', 'list_assets', self.list_assets, methods=['GET'])
        self.app.add_url_rule('/api/assets', 'upload_asset', self.upload_asset, methods=['POST'])
        self.app.add_url_rule('/api/assets/<category>/<name>', 'delete_asset', self.delete_asset, methods=['DELETE'])
        self.app.add_url_rule('/assets/<category>/<name>', 'serve_asset', self.serve_asset, methods=['GET'])
        self.app.add_url_rule('/api/privacy_mask', 'get_privacy_mask', self.get_privacy_mask, methods=['GET'])
        self.app.add_url_rule('/api/save_privacy_mask', 'save_privacy_mask', self.save_privacy_mask, methods=['POST'])

        
        # Focus Aid Routes
        self.app.add_url_rule('/api/focus-aid/start', 'start_focus_aid', self.start_focus_aid, methods=['POST'])
        self.app.add_url_rule('/api/focus-aid/stop', 'stop_focus_aid', self.stop_focus_aid, methods=['POST'])
        self.app.add_url_rule('/focus-aid/stream', 'focus_aid_stream', self.focus_aid_stream)

        # ONVIF (if enabled)
        if self.zerocam.config_manager.get('onvif', {}).get('enabled', False):
            from lib.onvif.onvif_service import ONVIFService
            onvif_service = ONVIFService(self.zerocam, self.zerocam.config_manager.get('onvif', {}))
            onvif_service.register_routes(self.app)

    # --- Route Implementations ---

    def login(self):
        if request.method == 'POST':
            username = request.form['username']
            password = request.form['password']
            
            security_config = self.zerocam.config_manager.get_raw('security', {})
            stored_username = security_config.get('username', 'admin')
            password_hash = security_config.get('password')

            if not password_hash:
                 self.logger.error("Password hash is not configured! Please set a password.")
                 flash("System is not configured correctly.")
                 return redirect(url_for('login'))

            user = User.get(username, security_config)

            if user and username == stored_username and check_password_hash(password_hash, password):
                login_user(user)
                return redirect(url_for('index'))
            
            flash('Invalid credentials.')
        
        return render_template('login.html')

    @login_required
    def logout(self):
        logout_user()
        return jsonify(success=True, message="Logout successful")

    @login_required
    def index(self):
        return render_template('index.html')

    @login_required
    def latest_image(self):
        return send_file(paths.LATEST_IMAGE, mimetype='image/jpeg')

    @login_required
    def stream_latest_image(self):
        # Assicurati che il percorso sia corretto
        # L'anteprima cambia ogni secondo: nessuna cache, altrimenti il
        # browser continuerebbe a mostrare il fotogramma già scaricato.
        return send_file(paths.STREAM_PREVIEW, mimetype='image/jpeg', max_age=0, conditional=False)

    @login_required
    def serve_page_template(self, page_name):
        safe_page_name = page_name.replace('.html', '')
        if not safe_page_name.isalnum():
            return "Invalid template name", 400
        template_path = os.path.join('pages', f'{safe_page_name}.html')
        return render_template(template_path)

    # --- API Method Implementations ---

    def _read_privacy_mask(self):
        """Privacy mask on disk, or an empty list when missing/corrupted."""
        try:
            with open(PRIVACY_MASK_PATH, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            self.logger.info(f"{PRIVACY_MASK_PATH} not found, returning empty list.")
            return []
        except json.JSONDecodeError:
            self.logger.error(f"{PRIVACY_MASK_PATH} is corrupted. Returning empty list.")
            return []

    @login_required
    def get_privacy_mask(self):
        """
        Loads and returns the privacy mask configuration from .privacy_mask.json.
        Returns an empty list if the file does not exist.
        """
        try:
            return jsonify(self._read_privacy_mask())
        except Exception as e:
            self.logger.error(f"Failed to load privacy mask: {e}", exc_info=True)
            return jsonify({"error": "Failed to load privacy mask"}), 500

    @login_required
    def save_privacy_mask(self):
        """
        Saves the provided JSON payload as the privacy mask configuration.
        """
        self.logger.info("Received request to save privacy mask.")

        data = request.json
        if data is None:
            return jsonify(success=False, message="No data or invalid JSON provided."), 400


        try:
            # Save the data to the specified file
            with open(PRIVACY_MASK_PATH, 'w') as f:
                json.dump(data, f, indent=4)
            
            self.logger.info("Privacy mask saved successfully to .privacy_mask.json")
            return jsonify(success=True, message="Privacy mask saved successfully.")
            
        except Exception as e:
            self.logger.error(f"Failed to save privacy mask: {e}", exc_info=True)
            return jsonify(success=False, message=f"An error occurred: {e}"), 500

    @login_required
    def restart(self):
        self.logger.warning("System reboot requested from web UI.")
        threading.Thread(target=lambda: os.system('sudo /sbin/reboot'), name="RebootThread").start()
        return jsonify(success=True, message="Riavvio del sistema in corso...")

    @login_required
    def change_password(self):
        data = request.json
        password_hash = self.zerocam.config_manager.get_raw('security', {}).get('password')

        if not check_password_hash(password_hash, data.get('current_password')):
            return jsonify(success=False, message="Current password incorrect."), 400

        config_to_save = json.loads(json.dumps(self.zerocam.config_manager.config))
        config_to_save['security']['password'] = generate_password_hash(data.get('new_password'))
        
        # Usa il metodo del config_manager per salvare
        self.zerocam.config_manager.save_config(config_to_save)
        return jsonify(success=True, message="Password changed successfully.")

    @login_required
    def handle_config(self):
        if request.method == 'POST':
            # Usa il metodo del config_manager per salvare
            success = self.zerocam.config_manager.save_config(request.json)
            if success:
                self.zerocam.apply_updated_config()
            # Dire "salvato" anche quando la scrittura è fallita lascia
            # l'utente convinto di avere una configurazione che non ha.
            return jsonify(success=success)
        else:
            # Restituisce la configurazione decifrata dal config_manager
            return jsonify(self.zerocam.config_manager.decrypted_config)

    @login_required
    def get_schema(self):
        try:
            with open('config_schema.json', 'r') as f:
                return jsonify(json.load(f))
        except FileNotFoundError:
            return jsonify({})

    @login_required
    def backup_config(self):
        """
        Returns the configuration as a passphrase-encrypted backup file.

        The passphrase never leaves this request: it only derives the key
        used to seal the payload.
        """
        data = request.json or {}
        try:
            envelope = config_backup.build(
                self.zerocam.config_manager.decrypted_config,
                self._read_privacy_mask(),
                data.get('passphrase') or '',
                get_version(),
            )
        except config_backup.BackupError as e:
            return jsonify(success=False, message=str(e)), 400
        except Exception as e:
            self.logger.error(f"Failed to build configuration backup: {e}", exc_info=True)
            return jsonify(success=False, message="Backup non riuscito, controlla i log."), 500

        filename = f"zerocam-backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
        self.logger.warning(f"Configuration backup downloaded as {filename}.")
        return Response(
            json.dumps(envelope, indent=2),
            mimetype='application/json',
            headers={'Content-Disposition': f'attachment; filename={filename}'},
        )

    @login_required
    def restore_config(self):
        """
        Replaces the configuration with the one held in a backup file.

        The security section is kept as it is on this machine, so the web
        credentials in use now keep working after the restore.
        """
        data = request.json or {}
        try:
            restored, mask = config_backup.read(data.get('backup'), data.get('passphrase') or '')
        except config_backup.BackupError as e:
            self.logger.warning(f"Configuration restore rejected: {e}")
            return jsonify(success=False, message=str(e)), 400

        current = self.zerocam.config_manager.config
        for section in config_backup.EXCLUDED_SECTIONS:
            if section in current:
                restored[section] = json.loads(json.dumps(current[section]))

        if not self.zerocam.config_manager.save_config(restored):
            return jsonify(success=False, message="Salvataggio della configurazione ripristinata non riuscito."), 500

        if mask is not None:
            try:
                with open(PRIVACY_MASK_PATH, 'w') as f:
                    json.dump(mask, f, indent=4)
            except Exception as e:
                self.logger.error(f"Restored config but failed to write privacy mask: {e}", exc_info=True)
                return jsonify(
                    success=False,
                    message="Configurazione ripristinata, ma la privacy mask non è stata scritta."
                ), 500

        self.zerocam.apply_updated_config()
        self.logger.warning("Configuration restored from backup file.")
        return jsonify(success=True, message="Configurazione ripristinata. Riavvia per applicarla del tutto.")

    @login_required
    def get_log(self):
        try:
            with open(paths.LOG_FILE, 'r') as f:
                return Response(f.read(), mimetype='text/plain')
        except FileNotFoundError:
            return Response("Log file not found.", status=404, mimetype='text/plain')

    @login_required
    def get_stats(self):
        # Accede allo storico e al buffer tramite lo stats_collector
        stats_collector = self.zerocam.stats_collector
        latest_stats = {}
        if stats_collector.stats_buffer:
            last_reading = stats_collector.stats_buffer[-1]
            latest_stats = {k: v for k, v in last_reading.items()}

        history = list(stats_collector.stats_history)
        return jsonify({"latest": latest_stats, "history": history})
        
    @login_required
    def get_capture_status(self):
        """
        Stato della cattura, con i secondi trascorsi.

        Di notte il bracketing dura minuti: senza il tempo trascorso la
        pagina sembra bloccata e non si distingue una cattura lunga da un
        guasto.
        """
        started = self.zerocam.capture_started_at
        elapsed = round(time.monotonic() - started) if started else 0
        return jsonify({"is_capturing": self.zerocam.capture_lock.locked(), "elapsed": elapsed})

    @login_required
    def get_stream_status(self):
        """
        Tells whether a live preview is available right now.

        'running' vale solo se il fotogramma condiviso è recente: lo stream
        si ferma a ogni scatto e il file su tmpfs resta lì, quindi la sola
        presenza non basta a dire che l'anteprima è viva.
        """
        camera = self.zerocam.components.camera
        running = bool(getattr(camera, 'running', False))
        fresh = False
        if running:
            try:
                fresh = (time.time() - os.path.getmtime(paths.STREAM_PREVIEW)) < 10
            except OSError:
                fresh = False

        enabled = (self.zerocam.config_manager.get('streamParameters', {}).get('enabled', False)
                   or self.zerocam.config_manager.get('onvif', {}).get('enabled', False))
        return jsonify(enabled=bool(enabled), running=running and fresh)

    @login_required
    def take_photo(self):
        self.logger.info("Manual photo trigger from web UI.")
        threading.Thread(target=self.zerocam.capture_job).start()
        return jsonify(success=True)
        
    # --- YouTube device flow ---

    @login_required
    def youtube_device_start(self):
        """
        Starts the OAuth device flow with the credentials from the form.

        The credentials come straight from the request so the user can
        authenticate before saving the configuration.
        """
        data = request.json or {}
        try:
            info = self.youtube_device_flow.start(data.get('client_id'), data.get('client_secret'))
            return jsonify(success=True, **info)
        except ValueError as e:
            return jsonify(success=False, error=str(e)), 400
        except Exception as e:
            self.logger.error(f"YouTube device flow start failed: {e}")
            return jsonify(success=False, error=str(e)), 400

    @login_required
    def youtube_device_poll(self):
        """Checks whether the user has completed the authorization yet."""
        try:
            return jsonify(self.youtube_device_flow.poll())
        except Exception as e:
            self.logger.error(f"YouTube device flow poll failed: {e}")
            return jsonify(status='failed', error=str(e))

    # --- Timelapse ---

    @login_required
    def get_timelapse(self):
        """Frame count, disk usage and outcome of the last build."""
        return jsonify(self.zerocam.components.timelapse.stats())

    @login_required
    def run_timelapse(self):
        """
        Triggers a build without waiting for the weekly schedule.

        Encoding takes minutes, so it runs in the background: the outcome
        is then readable from /api/timelapse.
        """
        upload = bool((request.json or {}).get('upload', True))
        self.logger.info(f"Manual timelapse build requested (upload={upload}).")
        threading.Thread(
            target=self.zerocam.components.timelapse.run,
            kwargs={'upload': upload},
            name='ManualTimelapseThread',
            daemon=True,
        ).start()
        return jsonify(success=True, message="Timelapse build started.")

    @login_required
    def timelapse_frames(self):
        """
        Without 'day', the list of days holding frames; with it, that day's
        frames. The gallery loads one image at a time, so only names travel.
        """
        timelapse = self.zerocam.components.timelapse
        day = request.args.get('day')
        if not day:
            return jsonify(days=timelapse.days())
        return jsonify(day=day, frames=timelapse.frames_for_day(day))

    @login_required
    def timelapse_frame(self, name):
        path = self.zerocam.components.timelapse.frame_path(name)
        if not path:
            return "Frame not found", 404
        # I fotogrammi non cambiano mai: lasciarli in cache al browser evita
        # di riscaricarli a ogni passaggio della galleria.
        return send_file(path, mimetype='image/jpeg', max_age=86400, conditional=True)

    # --- Pagina pubblica ---

    def _public_config(self):
        return self.zerocam.config_manager.get('settingsManager', {})

    def _public_enabled(self):
        return bool(self._public_config().get('public_page', False))

    def public_page(self):
        """
        Vetrina in sola lettura: ultimo scatto e nient'altro.

        Esiste per non dover esporre la console, che è amministrazione, a
        chi vuole soltanto guardare il panorama. Non legge la
        configurazione, non mostra il log e non accetta comandi.
        """
        if not self._public_enabled():
            return "Not found", 404

        config = self._public_config()
        device = self.zerocam.config_manager.get('deviceDetails', {})
        interval = self.zerocam.config_manager.get('cameraParameters', {}).get('shotInterval', 600)
        try:
            refresh = max(30, int(interval) // 2)
        except (TypeError, ValueError):
            refresh = 60

        return render_template(
            'public.html',
            title=config.get('public_title') or device.get('name') or 'zeroCAM',
            live_url=config.get('public_live_url', ''),
            refresh_seconds=refresh,
        )

    def public_image(self):
        if not self._public_enabled():
            return "Not found", 404
        if not os.path.exists(paths.LATEST_IMAGE):
            return "No image yet", 404
        # L'immagine cambia a ogni scatto: la pagina la richiede con un
        # parametro diverso, quindi qui non serve alcuna cache.
        return send_file(paths.LATEST_IMAGE, mimetype='image/jpeg', max_age=0, conditional=False)

    def public_info(self):
        """Quando è stato preso l'ultimo scatto. Nient'altro esce da qui."""
        if not self._public_enabled():
            return jsonify(error="not found"), 404
        try:
            captured = int(os.path.getmtime(paths.LATEST_IMAGE))
        except OSError:
            captured = 0
        return jsonify(captured_at=captured)

    # --- Assets ---

    @login_required
    def list_assets(self):
        """Elenco del materiale caricato, con le categorie disponibili."""
        category = request.args.get('category') or None
        try:
            return jsonify(
                success=True,
                assets=assets.listing(category),
                categories={key: value["label"] for key, value in assets.CATEGORIES.items()},
            )
        except assets.AssetError as e:
            return jsonify(success=False, error=str(e)), 400

    @login_required
    def upload_asset(self):
        """Riceve un file dal browser e lo mette fra gli assets."""
        uploaded = request.files.get('file')
        category = request.form.get('category', '')
        if not uploaded or not uploaded.filename:
            return jsonify(success=False, error="Nessun file ricevuto."), 400

        try:
            item = assets.save(category, uploaded.filename, uploaded)
        except assets.AssetError as e:
            return jsonify(success=False, error=str(e)), 400
        except Exception as e:
            self.logger.error(f"Asset upload failed: {e}", exc_info=True)
            return jsonify(success=False, error="Salvataggio non riuscito."), 500

        self.logger.info(f"Asset uploaded: {item['reference']} ({item['size']} bytes)")
        return jsonify(success=True, asset=item)

    @login_required
    def delete_asset(self, category, name):
        try:
            removed = assets.delete(category, name)
        except assets.AssetError as e:
            return jsonify(success=False, error=str(e)), 400

        if not removed:
            return jsonify(success=False, error="File non trovato."), 404
        self.logger.info(f"Asset deleted: {category}/{name}")
        return jsonify(success=True)

    @login_required
    def serve_asset(self, category, name):
        """Serve un asset all'interfaccia: anteprima audio e miniature."""
        path = assets.path(assets.reference(category, os.path.basename(name)))
        if not path:
            return "Asset not found", 404
        return send_file(path, conditional=True, max_age=3600)

    # --- Focus Aid ---
    
    @login_required
    def start_focus_aid(self):
        self.logger.info("Received request to start focus aid.")
        self.zerocam.pause_capture()
        self.focus_aid_running = True
        return jsonify(success=True)

    @login_required
    def stop_focus_aid(self):
        self.logger.info("Received request to stop focus aid.")
        self.focus_aid_running = False
        self.zerocam.resume_capture()
        return jsonify(success=True)

    @login_required
    def focus_aid_stream(self):
        # NOTA: Per semplicità, la funzione generatrice è un metodo separato.
        return Response(self._generate_focus_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')
        
    def _generate_focus_frames(self):
        """Generator function for the focus aid MJPEG stream."""
        self.logger.info("Starting focus aid stream generation...")
        
        # Accede alla camera tramite il component manager
        camera_component = self.zerocam.components.camera
        
        try:
            # NOTA: la logica di configurazione della camera è stata semplificata.
            # Se è necessaria una configurazione specifica, va gestita qui.
            camera_component.camera.start()
            time.sleep(2)

            while self.focus_aid_running:
                try:
                    image_buffer, metadata = camera_component.get_image()
                    image = Image.open(image_buffer)
                    draw = ImageDraw.Draw(image)

                    width, height = image.size
                    draw.line([(width/2, 0), (width/2, height)], fill="red", width=1)
                    draw.line([(0, height/2), (width, height/2)], fill="red", width=1)

                    output_stream = io.BytesIO()
                    image.save(output_stream, format="JPEG", quality=85)
                    frame_bytes = output_stream.getvalue()

                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
                    time.sleep(0.1)
                except Exception as e:
                    self.logger.error(f"Error in focus frame loop: {e}", exc_info=True)
                    break
        finally:
            if hasattr(camera_component, 'camera') and camera_component.camera.started:
                camera_component.camera.stop()
            self.logger.info("Focus aid stream generation stopped.")

    def _start_https(self, port, hostnames):
        """
        Avvia l'ascolto TLS in un thread e ritorna True se ci è riuscito.

        Waitress non parla TLS, quindi l'HTTPS lo serve cheroot, che lo fa
        nativamente ed è altrettanto adatto alla produzione. Un fallimento
        non è fatale: si resta sull'HTTP, meglio che nessuna interfaccia.
        """
        cert, key = tls.ensure_certificate(
            paths.CERT_FILE, paths.KEY_FILE, hostnames, self.logger
        )
        if not cert:
            return False

        try:
            from cheroot.wsgi import Server as CherootServer
        except ImportError:
            self.logger.error(
                "HTTPS requested but the 'cheroot' package is missing: staying on HTTP. "
                "Install it with pip install -r requirements.txt."
            )
            return False

        class QuietServer(CherootServer):
            """Zittisce il rumore che il redirect da HTTP a HTTPS produce."""

            def error_log(inner, msg='', level=logging.INFO, traceback=False):
                # cheroot annuncia la connessione interrotta come un
                # handshake caduto: qui invece e' voluta, e il redirect e'
                # gia' stato scritto a log dall'adattatore.
                if tls.REDIRECT_MARK in msg:
                    return
                # Un handshake che non arriva in fondo dipende dal client:
                # il browser che rifiuta il certificato autofirmato, una
                # scansione, una connessione caduta. Non e' un problema
                # della webcam e non deve riempirle il log.
                if 'during handshake' in msg:
                    self.logger.debug(f"HTTPS: {msg}")
                    return
                self.logger.log(level, f"HTTPS: {msg}", exc_info=traceback)

        try:
            server = QuietServer(('0.0.0.0', port), self.app, numthreads=4)
            server.ssl_adapter = tls.build_ssl_adapter(cert, key, self.logger)
            thread = threading.Thread(target=server.safe_start, name="HttpsThread", daemon=True)
            thread.start()
            self.logger.info(f"Web UI reachable over HTTPS on port {port}")
            return True
        except Exception as e:
            self.logger.error(f"Could not start the HTTPS listener on port {port}: {e}", exc_info=True)
            return False

    def run(self):
        """Starts the web server, over HTTP and optionally over HTTPS."""
        cfg = self.zerocam.config_manager.get('settingsManager', {})
        port = cfg.get('port', 8080)
        https_port = cfg.get('https_port', 8443)
        http_enabled = bool(cfg.get('http_enabled', True))

        https_running = False
        if cfg.get('https_enabled', False):
            https_running = self._start_https(https_port, cfg.get('https_hostnames', []))

        # ONVIF non parla TLS: spegnere l'HTTP lo mette fuori uso.
        if not http_enabled and self.zerocam.config_manager.get('onvif', {}).get('enabled', False):
            self.logger.warning(
                "HTTP is disabled but ONVIF is enabled: ONVIF clients speak plain HTTP "
                "and will not be able to reach the camera."
            )

        if not http_enabled and https_running:
            self.logger.info("HTTP disabled: the interface answers over HTTPS only.")
            # Il cookie di sessione può essere marcato come 'secure' solo
            # adesso: con l'HTTP acceso impedirebbe di autenticarsi su di esso.
            self.app.config['SESSION_COOKIE_SECURE'] = True
            while not self.zerocam.shutdown_flag.is_set():
                time.sleep(1)
            return

        if not http_enabled:
            self.logger.error("HTTP is disabled but HTTPS is not running: falling back to HTTP.")

        self.logger.info(f"Starting web UI and services on port {port}")
        serve(self.app, host='0.0.0.0', port=port, threads=4)


# --- Entry Point Function ---
def run_settings_manager(zerocam_instance):
    """
    This is the main entry point called by the ZeroCam application.
    It creates and runs the SettingsManager instance.
    """
    manager = SettingsManager(zerocam_instance)
    manager.run()