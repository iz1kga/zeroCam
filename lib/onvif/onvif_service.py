# -*- coding: utf-8 -*-
import os
import re
import socket
import time
from datetime import datetime, timezone
from functools import wraps

import xml.etree.ElementTree as ET
from flask import request, Response, send_file
from lxml import etree
from PIL import Image
from werkzeug.security import check_password_hash

from . import onvif_responses
from . import onvif_data

class ONVIFService:
    def __init__(self, zerocam_instance):
        self.zerocam = zerocam_instance
        self.logger = self.zerocam.logger
        
        # Usa il config_manager per un accesso coerente alla configurazione
        self.config = self.zerocam.config_manager.get_raw('onvif', {})
        self.enabled = self.config.get('enabled', False)
        
        if not self.enabled:
            return

        security_config = self.zerocam.config_manager.get_raw('security', {})
        self.auth_user = security_config.get('username')
        self.auth_pass_hash = security_config.get('password')

        self.announce_ip = self._get_local_ip()
        if not self.announce_ip:
             self.announce_ip = '127.0.0.1'
             self.logger.warning("ONVIF Announce IP is '127.0.0.1'. Device may not be discoverable.")
        else:
             self.logger.info(f"ONVIF: Announcing IP {self.announce_ip}")

        self.server_port = self.zerocam.config_manager.get_raw('settingsManager', {}).get('port', 8080)
        
        self.image_width, self.image_height = 1920, 1080
        self.update_resolution()
        
    def _get_local_ip(self):
        """Tries to determine the local IP of the machine for ONVIF announcement."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.1)
            s.connect(('8.8.8.8', 1))
            ip = s.getsockname()[0]
            s.close()
            self.logger.info(f"Dynamically detected local IP for ONVIF: {ip}")
            return ip
        except Exception as e:
            self.logger.error(f"Could not detect local IP dynamically: {e}. Fallback needed.")
            return None

    def onvif_auth_required(self, f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not self.auth_user or not self.auth_pass_hash:
                return f(*args, **kwargs)

            auth = request.authorization
            if not auth:
                self.logger.warning("ONVIF: Request missing authorization header.")
                return Response('Access Denied', 401, {'WWW-Authenticate': 'Basic realm="ONVIF Authentication"'})
            
            if auth.username == self.auth_user and check_password_hash(self.auth_pass_hash, auth.password):
                return f(*args, **kwargs)

            self.logger.warning(f"ONVIF: Failed login attempt for user '{auth.username}'.")
            return Response('Access Denied', 401, {'WWW-Authenticate': 'Basic realm="ONVIF Authentication"'})
        return decorated
        
    def update_resolution(self):
        """Reads resolution from the latest image available."""
        try:
            with Image.open('./shmem/stream_latest.jpg') as img:
                self.image_width, self.image_height = img.size
                self.logger.debug(f"ONVIF: Updated image resolution to {self.image_width}x{self.image_height}")
        except FileNotFoundError:
            self.logger.warning("ONVIF: stream_latest.jpg not found for resolution update. Using last known values.")
        except Exception as e:
            self.logger.error(f"ONVIF: Error reading stream_latest.jpg for resolution: {e}", exc_info=True)

    def generate_soap_response(self, body_content):
        """Helper to generate a complete SOAP XML response envelope."""
        return f"""<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope" xmlns:trt="http://www.onvif.org/ver10/media/wsdl" xmlns:tt="http://www.onvif.org/ver10/schema" xmlns:tds="http://www.onvif.org/ver10/device/wsdl">
<soap:Body>{body_content}</soap:Body>
</soap:Envelope>"""
    
    def register_routes(self, app):
        """Registers the Flask routes for the ONVIF service."""
        if not self.enabled:
            return
        
        self.logger.info("Registering ONVIF routes...")
        app.add_url_rule("/onvif/device_service", "device_service", self.onvif_auth_required(self.device_service), methods=["POST"])
        app.add_url_rule("/onvif/media_service", "media_service", self.onvif_auth_required(self.media_service), methods=["POST"])
        app.add_url_rule("/snapshot.jpg", "snapshot", self.onvif_auth_required(self.snapshot), methods=["GET"])
        self.logger.info("ONVIF routes registered successfully.")

    def _get_soap_action(self):
        """Extracts SOAP action from request headers for both SOAP 1.1 and 1.2."""
        soap_action = request.headers.get("SOAPAction", "").strip('"')
        if not soap_action:  # SOAP 1.2 uses Content-Type
            match = re.search(r'action="([^"]+)"', request.headers.get("Content-Type", ""), re.IGNORECASE)
            if match:
                soap_action = match.group(1).strip('"')
        return soap_action

    def device_service(self):
        try:
            soap_action = self._get_soap_action()
            self.logger.info(f"ONVIF Device Service: Received action '{soap_action}'")

            if "GetCapabilities" in soap_action:
                response_body = onvif_responses.get_capabilities_response(self.announce_ip, self.server_port)
            elif "GetHostname" in soap_action:
                response_body = onvif_responses.get_hostname_response()
            elif "GetDeviceInformation" in soap_action:
                response_body = onvif_responses.get_device_information_response()
            elif "GetSystemDateAndTime" in soap_action:
                response_body = onvif_responses.get_system_date_and_time_response(datetime.now(timezone.utc))
            elif "GetNetworkInterfaces" in soap_action:
                response_body = onvif_responses.get_network_interfaces_response(self.announce_ip)
            else:
                response_body = "<soap:Fault>Unknown action</soap:Fault>"
            
            return Response(self.generate_soap_response(response_body), content_type="application/soap+xml")
        except Exception as e:
            self.logger.error(f"Error in ONVIF device_service: {e}", exc_info=True)
            return Response(self.generate_soap_response("<soap:Fault>Internal Server Error</soap:Fault>"), status=500, content_type="application/soap+xml")

    def media_service(self):
        try:
            soap_action = self._get_soap_action()
            self.logger.info(f"ONVIF Media Service: Received action '{soap_action}'")
            self.update_resolution()

            if "GetProfiles" in soap_action:
                response_body = onvif_responses.get_profiles_response(onvif_data.PROFILES_DATA, self.image_width, self.image_height)
            elif "GetSnapshotUri" in soap_action:
                response_body = onvif_responses.get_snapshot_uri_response(self.announce_ip, self.server_port)
            elif "GetStreamUri" in soap_action:
                return Response(self.generate_soap_response("<soap:Fault>Action not supported for snapshot profile</soap:Fault>"), status=400, content_type="application/soap+xml")
            else: # Handle other media-related actions if needed, otherwise default to unknown
                response_body = "<soap:Fault>Unknown or unsupported action</soap:Fault>"

            return Response(self.generate_soap_response(response_body), content_type="application/soap+xml")
        except Exception as e:
            self.logger.error(f"Error in ONVIF media_service: {e}", exc_info=True)
            return Response(self.generate_soap_response("<soap:Fault>Internal Server Error</soap:Fault>"), status=500, content_type="application/soap+xml")

    def snapshot(self):
        image_path = './shmem/stream_latest.jpg'
        
        # Retry logic to wait for a complete JPG file
        for _ in range(10):  # Try for 500ms
            try:
                if os.path.exists(image_path) and os.path.getsize(image_path) > 2:
                    with open(image_path, 'rb') as f:
                        f.seek(-2, os.SEEK_END)
                        if f.read() == b'\xff\xd9': # JPEG End of Image marker
                            self.logger.info(f"ONVIF: Serving complete snapshot: {image_path}")
                            return send_file(image_path, mimetype="image/jpeg")
            except Exception:
                pass # Ignore errors during check, just retry
            
            time.sleep(0.05)
            
        self.logger.warning(f"ONVIF: Could not serve a complete snapshot from {image_path}. Serving fallback.")
        fallback_path = './latest.jpg'
        if os.path.exists(fallback_path):
            return send_file(fallback_path, mimetype="image/jpeg")

        self.logger.error("ONVIF snapshot: No snapshot image is available.")
        return "Snapshot not available.", 404