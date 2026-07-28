# -*- coding: utf-8 -*-
"""
Certificato TLS autofirmato per l'interfaccia web.

Una webcam su rete locale non ha un nome di dominio pubblico, quindi non
può ottenere un certificato riconosciuto: l'unica strada praticabile è
firmarselo da sé. Il browser mostrerà un avviso la prima volta - il
certificato non è attestato da nessuno - ma da lì in poi la connessione è
cifrata, e la password non attraversa più la rete in chiaro.

Il certificato viene creato al primo avvio e rigenerato solo se manca, se
è scaduto o se non copre più i nomi configurati.
"""

import datetime
import ipaddress
import os
import socket

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

# Dieci anni: un apparato in cassetta non ha nessuno che gli rinnovi i
# certificati, e un avviso di scadenza sarebbe solo un allarme in più su
# una connessione che il browser considera comunque non attestata.
VALIDITY_DAYS = 3650
# Margine entro cui si rigenera invece di aspettare la scadenza vera.
RENEW_BEFORE_DAYS = 30


def local_addresses():
    """Indirizzi IPv4 su cui il dispositivo può essere raggiunto."""
    addresses = {"127.0.0.1"}
    try:
        import psutil
        for interface in psutil.net_if_addrs().values():
            for address in interface:
                if address.family == socket.AF_INET and address.address:
                    addresses.add(address.address)
    except Exception:
        # Senza psutil il certificato copre comunque hostname e loopback
        pass
    return sorted(addresses)


def wanted_names(extra=None):
    """Nomi e indirizzi che il certificato deve coprire."""
    names = ["localhost"]
    try:
        hostname = socket.gethostname()
        if hostname:
            names.append(hostname)
            if "." not in hostname:
                names.append(hostname + ".local")
    except Exception:
        pass
    for value in extra or []:
        value = str(value).strip()
        if value:
            names.append(value)
    # Ordine stabile e senza doppioni, così il confronto con il certificato
    # esistente non cambia esito a ogni avvio.
    return sorted(set(names)) + local_addresses()


def _san_entries(names):
    entries = []
    for name in names:
        try:
            entries.append(x509.IPAddress(ipaddress.ip_address(name)))
        except ValueError:
            entries.append(x509.DNSName(name))
    return entries


def _certificate_covers(cert_path, names):
    """True se il certificato esistente è valido e copre tutti i nomi."""
    try:
        with open(cert_path, "rb") as f:
            cert = x509.load_pem_x509_certificate(f.read())
    except Exception:
        return False

    now = datetime.datetime.now(datetime.timezone.utc)
    not_after = cert.not_valid_after_utc
    if not_after - datetime.timedelta(days=RENEW_BEFORE_DAYS) < now:
        return False

    try:
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    except x509.ExtensionNotFound:
        return False

    covered = {str(v) for v in san.get_values_for_type(x509.DNSName)}
    covered |= {str(v) for v in san.get_values_for_type(x509.IPAddress)}
    return set(names).issubset(covered)


def fingerprint(cert_path):
    """Impronta SHA-256, quella che il browser mostra nell'avviso."""
    try:
        with open(cert_path, "rb") as f:
            cert = x509.load_pem_x509_certificate(f.read())
        digest = cert.fingerprint(hashes.SHA256())
        return ":".join(f"{b:02X}" for b in digest)
    except Exception:
        return "?"


def ensure_certificate(cert_path, key_path, extra_names=None, logger=None):
    """
    Garantisce che esista un certificato utilizzabile e ne ritorna i percorsi.

    Ritorna (cert_path, key_path) oppure (None, None) se la generazione non
    riesce: in quel caso chi chiama deve rinunciare all'HTTPS, non fermarsi.
    """
    names = wanted_names(extra_names)

    if os.path.isfile(cert_path) and os.path.isfile(key_path) and _certificate_covers(cert_path, names):
        if logger:
            logger.info(f"TLS certificate in use: {cert_path} (SHA-256 {fingerprint(cert_path)})")
        return cert_path, key_path

    try:
        os.makedirs(os.path.dirname(cert_path), exist_ok=True)
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, names[0][:64]),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "zeroCAM"),
        ])
        now = datetime.datetime.now(datetime.timezone.utc)
        certificate = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            # Un minuto indietro: l'orologio del Raspberry può essere
            # leggermente avanti rispetto a quello di chi si collega.
            .not_valid_before(now - datetime.timedelta(minutes=1))
            .not_valid_after(now + datetime.timedelta(days=VALIDITY_DAYS))
            .add_extension(x509.SubjectAlternativeName(_san_entries(names)), critical=False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .sign(key, hashes.SHA256())
        )

        with open(key_path, "wb") as f:
            f.write(key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            ))
        # La chiave privata non deve essere leggibile da altri utenti
        os.chmod(key_path, 0o600)

        with open(cert_path, "wb") as f:
            f.write(certificate.public_bytes(serialization.Encoding.PEM))

        if logger:
            logger.warning(
                f"Generated a self-signed TLS certificate for {', '.join(names)} "
                f"(SHA-256 {fingerprint(cert_path)})."
            )
        return cert_path, key_path

    except Exception as e:
        if logger:
            logger.error(f"Could not create the TLS certificate: {e}", exc_info=True)
        return None, None
