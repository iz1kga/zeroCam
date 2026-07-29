# -*- coding: utf-8 -*-
"""
Impianto comune ai test.

Due accorgimenti, entrambi necessari prima che i moduli vengano
importati: la cartella dei dati va spostata in un'area temporanea, perche'
lib.paths la calcola al momento dell'import e i test non devono scrivere
in quella vera; e picamera2 e libcamera vanno sostituiti con dei
segnaposto, perche' esistono solo sul Raspberry mentre il codice che
verifichiamo gira ovunque.
"""

import os
import sys
import tempfile
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

os.environ.setdefault("ZEROCAM_DATA_DIR", tempfile.mkdtemp(prefix="zerocam-tests-"))

for name in ("picamera2", "picamera2.encoders", "picamera2.outputs", "libcamera"):
    if name not in sys.modules:
        sys.modules[name] = types.ModuleType(name)
sys.modules["libcamera"].Transform = object
sys.modules["picamera2"].Picamera2 = object

import logging  # noqa: E402

import pytest  # noqa: E402


@pytest.fixture
def logger():
    """Un logger silenzioso: i test guardano gli effetti, non i messaggi."""
    log = logging.getLogger("zerocam-tests")
    log.addHandler(logging.NullHandler())
    log.propagate = False
    return log


@pytest.fixture
def metadata():
    """Metadati come quelli che libcamera restituisce con uno scatto."""
    return {
        "ExposureTime": 33234,
        "AnalogueGain": 8.0,
        "DigitalGain": 1.02,
        "ColourGains": (2.31, 1.47),
        "ColourTemperature": 3100,
        "Lux": 12.7,
        "AeLocked": True,
        "ScalerCrop": (0, 100, 4056, 2650),
    }
