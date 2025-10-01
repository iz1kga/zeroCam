# -*- coding: utf-8 -*-
import os
import json
import logging
import threading
import time
import io
from flask import Flask, Response, send_file, request, jsonify, render_template, redirect, url_for, flash
from waitress import serve
from PIL import Image, ImageDraw
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required

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
        
        self.app = Flask(__name__, template_folder='templates', static_folder='static')
        self.logger.info("Initializing SettingsManager...")
        self._setup_secret_key()
        self.logger.info("Flask secret key is set.")
        self._setup_login_manager()
        self._register_routes()

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
        self.app.add_url_rule('/api/log', 'get_log', self.get_log)
        self.app.add_url_rule('/api/stats', 'get_stats', self.get_stats)
        self.app.add_url_rule('/api/status/capture', 'get_capture_status', self.get_capture_status)
        self.app.add_url_rule('/api/take_photo', 'take_photo', self.take_photo, methods=['POST'])
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
        return send_file('./latest.jpg', mimetype='image/jpeg')

    @login_required
    def stream_latest_image(self):
        # Assicurati che il percorso sia corretto
        return send_file('./shmem/stream_latest.jpg', mimetype='image/jpeg')

    @login_required
    def serve_page_template(self, page_name):
        safe_page_name = page_name.replace('.html', '')
        if not safe_page_name.isalnum():
            return "Invalid template name", 400
        template_path = os.path.join('pages', f'{safe_page_name}.html')
        return render_template(template_path)

    # --- API Method Implementations ---

    @login_required
    def get_privacy_mask(self):
        """
        Loads and returns the privacy mask configuration from .privacy_mask.json.
        Returns an empty list if the file does not exist.
        """
        try:
            with open('.privacy_mask.json', 'r') as f:
                data = json.load(f)
                return jsonify(data)
        except FileNotFoundError:
            self.logger.info(".privacy_mask.json not found, returning empty list.")
            return jsonify([])
        except json.JSONDecodeError:
            self.logger.error(".privacy_mask.json is corrupted. Returning empty list.")
            return jsonify([])
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
            with open('.privacy_mask.json', 'w') as f:
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
            return jsonify(success=True)
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
    def get_log(self):
        try:
            with open('./logs/zerocam.log', 'r') as f:
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
        return jsonify({"is_capturing": self.zerocam.capture_lock.locked()})

    @login_required
    def take_photo(self):
        self.logger.info("Manual photo trigger from web UI.")
        threading.Thread(target=self.zerocam.capture_job).start()
        return jsonify(success=True)
        
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

    def run(self):
        """Starts the Waitress server for the Flask application."""
        port = self.zerocam.config_manager.get('settingsManager', {}).get('port', 8080)
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