# -*- coding: utf-8 -*-
"""Certificato autofirmato e riconoscimento delle richieste in chiaro."""

import datetime
import os
import stat

from cryptography import x509

from lib import tls


def genera(tmp_path, nomi=None, logger=None):
    cert = str(tmp_path / "zerocam.crt")
    key = str(tmp_path / "zerocam.key")
    return tls.ensure_certificate(cert, key, nomi, logger)


def test_certificato_creato_con_i_nomi_richiesti(tmp_path, logger):
    cert, key = genera(tmp_path, ["webcam.esempio.it"], logger)
    assert cert and key

    certificate = x509.load_pem_x509_certificate(open(cert, "rb").read())
    san = certificate.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    dns = san.get_values_for_type(x509.DNSName)
    ip = [str(v) for v in san.get_values_for_type(x509.IPAddress)]

    assert "webcam.esempio.it" in dns
    assert "localhost" in dns
    assert "127.0.0.1" in ip, "senza il loopback non si prova nemmeno da locale"


def test_chiave_privata_non_leggibile_da_altri(tmp_path, logger):
    _, key = genera(tmp_path, logger=logger)
    assert stat.S_IMODE(os.stat(key).st_mode) == 0o600


def test_il_certificato_valido_viene_riusato(tmp_path, logger):
    cert, _ = genera(tmp_path, ["webcam.esempio.it"], logger)
    impronta = tls.fingerprint(cert)
    genera(tmp_path, ["webcam.esempio.it"], logger)
    assert tls.fingerprint(cert) == impronta, "rigenerarlo farebbe ricomparire l'avviso del browser"


def test_un_nome_nuovo_lo_rigenera(tmp_path, logger):
    cert, _ = genera(tmp_path, ["webcam.esempio.it"], logger)
    impronta = tls.fingerprint(cert)
    genera(tmp_path, ["webcam.esempio.it", "altro.esempio.it"], logger)
    assert tls.fingerprint(cert) != impronta


def test_validita_lunga(tmp_path, logger):
    cert, _ = genera(tmp_path, logger=logger)
    certificate = x509.load_pem_x509_certificate(open(cert, "rb").read())
    residua = certificate.not_valid_after_utc - datetime.datetime.now(datetime.timezone.utc)
    assert residua.days > 3000, "un apparato in cassetta non ha chi gli rinnovi i certificati"


def test_nomi_sempre_nello_stesso_ordine():
    """Un ordine instabile farebbe rigenerare il certificato a ogni avvio."""
    assert tls.wanted_names(["b.esempio.it", "a.esempio.it"]) == \
           tls.wanted_names(["a.esempio.it", "b.esempio.it"])


def test_nomi_vuoti_ignorati():
    nomi = tls.wanted_names(["", "   ", "buono.esempio.it"])
    assert "buono.esempio.it" in nomi
    assert "" not in nomi


def test_il_freno_al_log_lascia_passare_il_primo():
    """Un client che bussa ogni secondo non deve riempire il log."""
    freno = tls._Throttle()
    assert freno.allow(("1.2.3.4", "/snapshot.jpg")) is True
    assert freno.allow(("1.2.3.4", "/snapshot.jpg")) is False
    # Un percorso diverso merita comunque la sua riga
    assert freno.allow(("1.2.3.4", "/altro")) is True
    # E un altro client pure
    assert freno.allow(("5.6.7.8", "/snapshot.jpg")) is True


def test_il_freno_non_cresce_senza_limite():
    freno = tls._Throttle()
    for i in range(300):
        freno.allow((f"10.0.0.{i}", "/x"))
    assert len(freno._seen) <= 257
