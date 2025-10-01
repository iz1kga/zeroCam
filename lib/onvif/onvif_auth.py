import base64
import hashlib
from datetime import datetime, timezone, timedelta
from lxml import etree

# Enum per un ritorno pulito dello stato di autenticazione
from enum import Enum
class AuthResult(Enum):
    AUTHENTICATED = 1
    NOT_AUTHENTICATED = 2
    AUTH_NOT_REQUIRED = 3 # Header non presente

def verify_request(xml_data, username, password, logger=None):
    """
    Verifica una richiesta ONVIF usando WS-Security Digest.
    Restituisce un Enum AuthResult.
    """
    try:
        # Namespace necessari per trovare gli elementi
        ns = {
            'soap': 'http://www.w3.org/2003/05/soap-envelope',
            'wsse': 'http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd',
            'wsu': 'http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd'
        }

        # Parsing del corpo XML della richiesta
        root = etree.fromstring(xml_data)
        security_header = root.find('.//wsse:Security', namespaces=ns)

        # Se non c'è l'header di sicurezza, la richiesta non è autenticata
        if security_header is None:
            logger.info("No WS-Security header found; authentication not required.")
            return AuthResult.AUTH_NOT_REQUIRED

        # Estrai tutti i componenti necessari
        username_token = security_header.find('.//wsse:UsernameToken', namespaces=ns)
        if username_token is None:
            logger.info("WS-Security header found but no UsernameToken; authentication failed.")
            return AuthResult.NOT_AUTHENTICATED # Header presente ma malformato

        req_username = username_token.find('wsse:Username', namespaces=ns).text
        req_digest = username_token.find('wsse:Password', namespaces=ns).text
        
        # Il Nonce può avere diversi encoding, ma di solito è Base64
        nonce_element = username_token.find('wsse:Nonce', namespaces=ns)
        req_nonce_b64 = nonce_element.text
        
        created_element = username_token.find('wsu:Created', namespaces=ns)
        req_created_str = created_element.text

        # 1. Controlla se l'utente corrisponde
        if req_username != username:
            logger.info(f"Username mismatch: expected '{username}', got '{req_username}'")
            return AuthResult.NOT_AUTHENTICATED

        # 2. Controlla la freschezza del timestamp (es. +/- 5 minuti)
        try:
            req_created_dt = datetime.fromisoformat(req_created_str.replace('Z', '+00:00'))
            now_utc = datetime.now(timezone.utc)
            if abs((now_utc - req_created_dt).total_seconds()) > 300:
                # La richiesta è troppo vecchia o da un client con orologio non sincronizzato
                logger.info(f"Timestamp out of range: {req_created_str}")
                return AuthResult.NOT_AUTHENTICATED
        except ValueError:
            return AuthResult.NOT_AUTHENTICATED # Timestamp malformato

        # 3. Ricalcola il Digest sul server
        # La formula è: Base64(SHA1(Nonce + Created + Password))
        # Il Nonce ricevuto è in Base64, quindi va prima decodificato.
        nonce_bytes = base64.b64decode(req_nonce_b64)
        created_bytes = req_created_str.encode('utf-8')
        password_bytes = password.encode('utf-8')
        
        # Concatena i bytes
        digest_input = nonce_bytes + created_bytes + password_bytes
        
        # Calcola l'hash SHA1 e poi encodalo in Base64
        sha1_hash = hashlib.sha1(digest_input).digest()
        server_digest = base64.b64encode(sha1_hash).decode('utf-8')
        
        # 4. Confronta il digest calcolato con quello ricevuto
        if server_digest == req_digest:
            logger.info("Authentication successful.")
            return AuthResult.AUTHENTICATED
        else:
            logger.info("Password digest mismatch; authentication failed.")
            return AuthResult.NOT_AUTHENTICATED

    except Exception:
        # Qualsiasi errore nel parsing o nella verifica risulta in un fallimento
        return AuthResult.NOT_AUTHENTICATED