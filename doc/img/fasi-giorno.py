#!/usr/bin/env python3
"""
Disegna l'elevazione del Sole in una giornata e le soglie che separano le
quattro fasi usate da zeroCAM. Rigenerare con doc/img/genera-diagrammi.sh
"""

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

SUN_OFFSET = -2.5   # deviceDetails.sunRiseOffset / sunSetOffset
TWILIGHT = -6.0     # deviceDetails.dawnOffset / duskOffset

# Curva verosimile per una giornata di mezza stagione a 45° di latitudine:
# serve a illustrare le soglie, non a fare astronomia.
ore = np.linspace(0, 24, 1000)
elevazione = 45 * np.sin(np.pi * (ore - 6.2) / 12.4)

fig, ax = plt.subplots(figsize=(9, 4.2))
ax.plot(ore, elevazione, color="#33445c", linewidth=2, zorder=3)
ax.axhline(0, color="#999999", linewidth=0.8, zorder=1)
ax.axhline(SUN_OFFSET, color="#c07830", linewidth=1.2, linestyle="--", zorder=2)
ax.axhline(TWILIGHT, color="#7a5aa0", linewidth=1.2, linestyle="--", zorder=2)

ax.text(12, SUN_OFFSET + 1.5, f"sunRiseOffset / sunSetOffset = {SUN_OFFSET}°",
        ha="center", va="bottom", fontsize=9, color="#c07830")
ax.text(12, TWILIGHT - 1.5, f"dawnOffset / duskOffset = {TWILIGHT}°",
        ha="center", va="top", fontsize=9, color="#7a5aa0")

# Le fasi, ricavate dalle intersezioni della curva con le soglie
def attraversamenti(soglia):
    segni = np.sign(elevazione - soglia)
    indici = np.where(np.diff(segni) != 0)[0]
    return [ore[i] for i in indici]

alba_civ, tramonto_civ = attraversamenti(TWILIGHT)
alba_sun, tramonto_sun = attraversamenti(SUN_OFFSET)

fasi = [
    ("notte", 0, alba_civ, "#dfe3ea"),
    ("dawn", alba_civ, alba_sun, "#f0e2cf"),
    ("day", alba_sun, tramonto_sun, "#f7f3d9"),
    ("dusk", tramonto_sun, tramonto_civ, "#f0e2cf"),
    ("notte", tramonto_civ, 24, "#dfe3ea"),
]
for nome, inizio, fine, colore in fasi:
    ax.axvspan(inizio, fine, color=colore, zorder=0)
    centro = (inizio + fine) / 2
    if fine - inizio > 1.5:
        ax.text(centro, -40, nome, ha="center", fontsize=10, color="#33445c")
    else:
        # dawn e dusk durano poco: l'etichetta va portata fuori dalla banda
        ax.annotate(nome, xy=(centro, -34), xytext=(centro, -44),
                    ha="center", fontsize=10, color="#33445c",
                    arrowprops=dict(arrowstyle="-", color="#8a8a8a", linewidth=0.8))

ax.set_xlim(0, 24)
ax.set_ylim(-50, 52)
ax.set_xticks(range(0, 25, 3))
ax.set_xlabel("Ora del giorno")
ax.set_ylabel("Elevazione del Sole (gradi)")
ax.spines[["top", "right"]].set_visible(False)
fig.tight_layout()

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fasi-giorno.png")
fig.savefig(out, dpi=160)
print(f"Creato {out}")
