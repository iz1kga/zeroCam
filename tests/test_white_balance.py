# -*- coding: utf-8 -*-
"""
Bilanciamento del bianco della cattura.

La regola da difendere e' una sola: i guadagni fissi valgono soltanto con
la modalita' Manuale, e le chiavi di zeroCAM non devono mai finire fra i
controlli passati a libcamera, che le rifiuterebbe.
"""

import cameras


def apply(logger, params, controls=None):
    device = cameras.PiCameraDevice.__new__(cameras.PiCameraDevice)
    device.logger = logger
    return device._apply_white_balance(dict(controls or {}), params)


def test_automatico_di_default(logger):
    controls = apply(logger, {})
    assert controls["AwbEnable"] is True
    assert controls["AwbMode"] == 0
    assert "ColourGains" not in controls


def test_modalita_preimpostata(logger):
    controls = apply(logger, {"AwbMode": 5})
    assert controls["AwbEnable"] is True
    assert controls["AwbMode"] == 5


def test_manuale_con_guadagni_validi(logger):
    controls = apply(logger, {"AwbMode": cameras.AWB_MANUAL,
                              "ColourGainRed": 2.4, "ColourGainBlue": 1.3})
    assert controls["AwbEnable"] is False
    assert controls["ColourGains"] == (2.4, 1.3)


def test_il_manuale_ripulisce_i_controlli_ricevuti(logger):
    """
    AwbMode 7 e' una voce del nostro menu, non una modalita' di libcamera:
    se un chiamante passa i parametri di fase come controlli, va tolta,
    altrimenti finirebbe in set_controls e farebbe fallire lo scatto.
    """
    controls = apply(logger,
                     {"AwbMode": cameras.AWB_MANUAL, "ColourGainRed": 2.4, "ColourGainBlue": 1.3},
                     controls={"AwbMode": cameras.AWB_MANUAL, "Sharpness": 4})
    assert "AwbMode" not in controls
    assert controls["Sharpness"] == 4, "il resto dei controlli non si tocca"


def test_manuale_senza_guadagni_torna_automatico(logger):
    """Meglio uno scatto automatico che uno con i colori a caso."""
    controls = apply(logger, {"AwbMode": cameras.AWB_MANUAL, "ColourGainRed": 2.4})
    assert controls["AwbEnable"] is True
    assert controls["AwbMode"] == 0
    assert "ColourGains" not in controls


def test_guadagni_ignorati_fuori_dal_manuale(logger):
    controls = apply(logger, {"AwbMode": 2, "ColourGainRed": 2.4, "ColourGainBlue": 1.3})
    assert controls["AwbEnable"] is True
    assert "ColourGains" not in controls


def test_modalita_non_numerica(logger):
    controls = apply(logger, {"AwbMode": "auto"})
    assert controls["AwbEnable"] is True
    assert controls["AwbMode"] == 0


def test_guadagni_negativi_o_nulli(logger):
    for red, blue in ((0, 1.3), (2.4, 0), (-1, -1)):
        controls = apply(logger, {"AwbMode": cameras.AWB_MANUAL,
                                  "ColourGainRed": red, "ColourGainBlue": blue})
        assert controls["AwbEnable"] is True, (red, blue)
