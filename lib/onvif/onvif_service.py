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
from .onvif_auth import verify_request, AuthResult

class ONVIFService:
    def __init__(self, zerocam_instance, config):
        self.zerocam = zerocam_instance
        self.logger = self.zerocam.logger
        
        self.config = config
        self.enabled = self.config.get('enabled', False)
        
        if not self.enabled:
            return

        self.auth_user = self.config.get('username')
        self.auth_pass = self.config.get('password')
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

        
    def update_resolution(self):
        """Reads resolution from the latest image available, with retries."""
        max_retries = 4  # Prova un totale di 4 volte
        for attempt in range(max_retries):
            try:
                with Image.open('./shmem/stream_latest.jpg') as img:
                    self.image_width, self.image_height = img.size
                    self.logger.debug(f"ONVIF: Updated image resolution to {self.image_width}x{self.image_height}")
                    return  # Se ha successo, esce immediatamente dalla funzione

            except FileNotFoundError:
                # Se questa è l'ultima iterazione, registra il warning finale
                if attempt == max_retries - 1:
                    self.logger.warning("ONVIF: stream_latest.jpg not found after retries. Using last known values.")
            except Exception as e:
                # Se questa è l'ultima iterazione, registra l'errore finale
                if attempt == max_retries - 1:
                    self.logger.error(f"ONVIF: Error reading stream_latest.jpg after retries: {e}", exc_info=True)
            
            # Se non siamo all'ultimo tentativo, attendi 25ms prima di riprovare
            if attempt < max_retries - 1:
                time.sleep(0.025)

    def generate_soap_response(self, body_content):
        """Helper to generate a complete SOAP XML response envelope."""
        return f"""<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope" xmlns:trt="http://www.onvif.org/ver10/media/wsdl" xmlns:tt="http://www.onvif.org/ver10/schema" xmlns:tds="http://www.onvif.org/ver10/device/wsdl">
<soap:Body>{body_content}</soap:Body>
</soap:Envelope>"""

    def http_basic_auth_required(self, f):
        """Decoratore per la protezione di endpoint HTTP con Basic Authentication."""
        @wraps(f)
        def decorated(*args, **kwargs):
            if not self.auth_user or not self.auth_pass:
                return f(*args, **kwargs)

            auth = request.authorization
            
            if not auth:
                self.logger.warning(f"SNAPSHOT: Richiesta a {request.path} senza header di autenticazione.")
                return Response(
                    'Accesso negato: Autenticazione richiesta.', 401,
                    {'WWW-Authenticate': 'Basic realm="Snapshot Access"'})
            
            if auth.username == self.auth_user and auth.password == self.auth_pass:
                return f(*args, **kwargs)

            self.logger.warning(f"SNAPSHOT: Tentativo di accesso fallito per l'utente '{auth.username}'.")
            return Response(
                'Accesso negato: Credenziali non valide.', 401,
                {'WWW-Authenticate': 'Basic realm="Snapshot Access"'})
        return decorated
    
    def register_routes(self, app):
        """Registers the Flask routes for the ONVIF service."""
        if not self.enabled:
            return
        
        self.logger.info("Registering ONVIF routes...")
        # Le rotte ora puntano direttamente alle funzioni senza decoratori di autenticazione
        app.add_url_rule("/onvif/device_service", "device_service", self.device_service, methods=["POST"])
        app.add_url_rule("/onvif/media_service", "media_service", self.media_service, methods=["POST"])
        if self.config.get('allow_unsecure', False):
            self.logger.info("ONVIF: Allowing unauthenticated access to /snapshot.jpg as per configuration.")
            app.add_url_rule("/snapshot.jpg", "snapshot", self.snapshot, methods=["GET"])
        else:
            self.logger.info("ONVIF: Protecting /snapshot.jpg with HTTP Basic Auth as per configuration.")
            app.add_url_rule("/snapshot.jpg", "snapshot", self.http_basic_auth_required(self.snapshot), methods=["GET"])
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
            auth_status = verify_request(request.data, self.auth_user, self.auth_pass, self.logger)

            ANONYMOUS_ACTIONS = [
            "GetCapabilities", "GetDeviceInformation", "GetHostname",
            "GetSystemDateAndTime", "GetNetworkInterfaces", "GetDNS"
            ]
            is_anonymous_action = any(action in soap_action for action in ANONYMOUS_ACTIONS)
            if not is_anonymous_action and auth_status == AuthResult.AUTH_NOT_REQUIRED:
                self.logger.warning(f"ONVIF: Action '{soap_action}' requires authentication, but none was provided.")
                fault_body = onvif_responses.create_fault_response("Authentication Required")
                return Response(self.generate_soap_response(fault_body), status=200, content_type="application/soap+xml")


            response_body = ""
            if "GetCapabilities" in soap_action:
                response_body = onvif_responses.get_capabilities_response(self.announce_ip, self.server_port)
            elif "GetDeviceInformation" in soap_action:
                response_body = onvif_responses.get_device_information_response()
            elif "GetHostname" in soap_action:
                response_body = onvif_responses.get_hostname_response()
            elif "GetSystemDateAndTime" in soap_action:
                response_body = onvif_responses.get_system_date_and_time_response(datetime.now(timezone.utc))
            elif "GetNetworkInterfaces" in soap_action:
                response_body = onvif_responses.get_network_interfaces_response(self.announce_ip)
            else:
                self.logger.warning(f"SOAP action '{soap_action}' is known but not implemented.")
                response_body = "<soap:Fault>Action not implemented</soap:Fault>"
            
            return Response(self.generate_soap_response(response_body), content_type="application/soap+xml")

        except Exception as e:
            self.logger.error(f"Error in ONVIF device_service: {e}", exc_info=True)
            return Response(self.generate_soap_response("<soap:Fault>Internal Server Error</soap:Fault>"), status=500, content_type="application/soap+xml")

    def media_service(self):
        try:
            soap_action = self._get_soap_action()
            self.logger.info(f"ONVIF Media Service: Received action '{soap_action}'")
            self.update_resolution()

            auth_status = verify_request(request.data, self.auth_user, self.auth_pass, self.logger)

            ANONYMOUS_ACTIONS = []
            is_anonymous_action = any(action in soap_action for action in ANONYMOUS_ACTIONS)
            if not is_anonymous_action and auth_status == AuthResult.AUTH_NOT_REQUIRED:
                self.logger.warning(f"ONVIF: Action '{soap_action}' requires authentication, but none was provided.")
                fault_body = onvif_responses.create_fault_response("Authentication Required")
                return Response(self.generate_soap_response(fault_body), status=200, content_type="application/soap+xml")

            response_body = ""
            if "GetProfiles" in soap_action:
                    response_body = onvif_responses.get_profiles_response(onvif_data.PROFILES_DATA, self.image_width, self.image_height)
                    soap_response = self.generate_soap_response(response_body)
                    return Response(soap_response, content_type="application/soap+xml")

            elif "GetVideoSources" in soap_action:
                response_body = onvif_responses.get_video_sources_response(onvif_data.PROFILES_DATA, self.image_width, self.image_height)
                return Response(self.generate_soap_response(response_body), content_type="application/soap+xml")
            
            elif "GetVideoSourceConfiguration" in soap_action:
                requested_config_token = ""
                try:
                    body_xml = etree.fromstring(request.data)
                    ns = {'trt': 'http://www.onvif.org/ver10/media/wsdl', 'tt': 'http://www.onvif.org/ver10/schema'}
                    token_element = body_xml.find('.//trt:ConfigurationToken', namespaces=ns)
                    if token_element is None:
                        token_element = body_xml.find('.//tt:ConfigurationToken', namespaces=ns)
                    
                    if token_element is not None and token_element.text is not None:
                        requested_config_token = token_element.text
                    else:
                        self.logger.warning("ConfigurationToken non trovato nella richiesta GetVideoSourceConfiguration.")
                        fault_body = "<soap:Fault><soap:Reason><soap:Text xml:lang=\"en\">InvalidArgs - ConfigurationToken missing</soap:Text></soap:Reason></soap:Fault>"
                        return Response(self.generate_soap_response(fault_body), status=400, content_type="application/soap+xml")
                    
                    self.logger.info(f"Richiesto VideoSourceConfigurationToken: '{requested_config_token}'")
                except Exception as e_parse:
                    self.logger.error(f"Errore nel parsing della richiesta GetVideoSourceConfiguration: {e_parse}")
                    fault_body = "<soap:Fault><soap:Reason><soap:Text xml:lang=\"en\">Sender - Error parsing request</soap:Text></soap:Reason></soap:Fault>"
                    return Response(self.generate_soap_response(fault_body), status=400, content_type="application/soap+xml")


                response_body = onvif_responses.get_video_source_configuration_response(requested_config_token, self.image_width, self.image_height)
                return Response(self.generate_soap_response(response_body), content_type="application/soap+xml")

            elif "GetAudioSources" in soap_action:
                response_body = """
                <trt:GetAudioSourcesResponse xmlns:trt="http://www.onvif.org/ver10/media/wsdl">
                    </trt:GetAudioSourcesResponse>
                """
                return Response(self.generate_soap_response(response_body), content_type="application/soap+xml")

            elif "GetProfile" in soap_action: # Azione GetProfile (singolare)                    
                requested_profile_token = ""
                try:
                    body_xml = etree.fromstring(request.data)
                    ns = {'trt': 'http://www.onvif.org/ver10/media/wsdl'}
                    token_element = body_xml.find('.//trt:ProfileToken', namespaces=ns)
                    if token_element is not None and token_element.text is not None:
                        requested_profile_token = token_element.text
                        self.logger.info(f"Richiesto ProfileToken: '{requested_profile_token}'")
                    else:
                        self.logger.warning("ProfileToken non trovato nella richiesta GetProfile.")
                        fault_body = "<soap:Fault><soap:Reason><soap:Text xml:lang=\"en\">InvalidArgs - ProfileToken missing</soap:Text></soap:Reason></soap:Fault>"
                        return Response(self.generate_soap_response(fault_body), status=400, content_type="application/soap+xml")
                except Exception as e_parse:
                    self.logger.error(f"Errore nel parsing della richiesta GetProfile: {e_parse}")
                    fault_body = "<soap:Fault><soap:Reason><soap:Text xml:lang=\"en\">Sender - Error parsing request</soap:Text></soap:Reason></soap:Fault>"
                    return Response(self.generate_soap_response(fault_body), status=400, content_type="application/soap+xml")
                
                response_body = onvif_responses.get_profile_response(onvif_data.PROFILES_DATA, requested_profile_token, self.image_width, self.image_height)
                return Response(self.generate_soap_response(response_body), content_type="application/soap+xml")

            elif "GetVideoEncoderConfigurationOptions" in soap_action:
                ns = {'trt': 'http://www.onvif.org/ver10/media/wsdl'}
                root = ET.fromstring(request.data)
                token_element = root.find('.//trt:ConfigurationToken', ns)
                if token_element is None:
                    token_element = root.find('.//trt:ProfileToken', ns)

                requested_token = token_element.text if token_element is not None else next(iter(onvif_data.PROFILES_DATA.keys()))
                self.logger.info(f"Richiesto VideoEncoderConfigurationOptions per il token: {requested_token}")
                response_body = onvif_responses.get_video_encoder_configuration_options(onvif_data.ENCODER_OPTIONS_DATA, requested_token, self.image_width, self.image_height)
                return Response(self.generate_soap_response(response_body),
                                content_type="application/soap+xml")
        
            elif "GetVideoEncoderConfigurations" in soap_action:
                response_body = onvif_responses.get_video_encoder_configurations(onvif_data.PROFILES_DATA, self.image_width, self.image_height)
                return Response(self.generate_soap_response(response_body),
                                content_type="application/soap+xml")
            
            elif "GetVideoEncoderConfiguration" in soap_action:
                ns = {'trt': 'http://www.onvif.org/ver10/media/wsdl'}
                root = ET.fromstring(request.data)
                token_element = root.find('.//trt:ConfigurationToken', ns)
                if token_element is None:
                    token_element = root.find('.//trt:ProfileToken', ns)

                requested_token = token_element.text if token_element is not None else next(iter(onvif_data.PROFILES_DATA.keys()))
                response_body = onvif_responses.get_video_encoder_configuration(onvif_data.PROFILES_DATA, requested_token, self.image_width, self.image_height)
                return Response(self.generate_soap_response(response_body),
                                content_type="application/soap+xml")

            elif "SetVideoEncoderConfiguration" in soap_action:
                self.logger.info("Gestione azione Media: SetVideoEncoderConfiguration")
                response_body = """
                <trt:SetVideoEncoderConfigurationResponse/>
                """
                return Response(self.generate_soap_response(response_body), content_type="application/soap+xml")
            
            elif "GetStreamUri" in soap_action:
                response_body = onvif_responses.handle_get_stream_uri(onvif_data.PROFILES_DATA, request.data, self.announce_ip, self.rtsp_port, self.logger)
                soap_response = self.generate_soap_response(response_body)
                if response_body is None:
                    return Response(self.generate_soap_response("<soap:Fault>Not Supported</soap:Fault>"),
                                    status=400, content_type="application/soap+xml")
                else:
                    return Response(soap_response, content_type="application/soap+xml")

            elif "GetSnapshotUri" in soap_action:
                body_xml = etree.fromstring(request.data)
                ns = {'trt': 'http://www.onvif.org/ver10/media/wsdl'}
                token_element = body_xml.find('.//trt:ProfileToken', namespaces=ns)
                token = token_element.text if token_element is not None else ''
                self.logger.info(f"Richiesto GetSnapshotUri per il token: {token}")
                if "Profile_Snapshot" in token:
                    response_body = onvif_responses.get_snapshot_uri_response(self.announce_ip, self.server_port)
                else:
                    response_body = ""
                return Response(self.generate_soap_response(response_body),
                                content_type="application/soap+xml")
            else:
                return Response(self.generate_soap_response("<soap:Fault>Unknown action</soap:Fault>"),
                                status=400, content_type="application/soap+xml")

        except Exception as e:
            self.logger.error(f"Error in ONVIF media_service: {e}", exc_info=True)
            return Response(self.generate_soap_response("<soap:Fault>Internal Server Error</soap:Fault>"), status=500, content_type="application/soap+xml")

    def snapshot(self):
        image_path = './shmem/stream_latest.jpg'
        
        for _ in range(10):
            try:
                if os.path.exists(image_path) and os.path.getsize(image_path) > 2:
                    with open(image_path, 'rb') as f:
                        f.seek(-2, os.SEEK_END)
                        if f.read() == b'\xff\xd9':
                            self.logger.info(f"ONVIF: Serving complete snapshot: {image_path}")
                            return send_file(image_path, mimetype="image/jpeg")
            except Exception:
                pass
            
            time.sleep(0.05)
            
        self.logger.warning(f"ONVIF: Could not serve a complete snapshot from {image_path}. Serving fallback.")
        fallback_path = './latest.jpg'
        if os.path.exists(fallback_path):
            return send_file(fallback_path, mimetype="image/jpeg")

        self.logger.error("ONVIF snapshot: No snapshot image is available.")
        return "Snapshot not available.", 404