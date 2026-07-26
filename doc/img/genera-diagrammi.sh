#!/usr/bin/env bash
#
# Rigenera i diagrammi del manuale dai rispettivi sorgenti.
# Serve graphviz e matplotlib:  sudo apt install graphviz python3-matplotlib
#
set -euo pipefail
cd "$(dirname "$0")"

for src in *.dot; do
    dot -Tpng -Gdpi=160 "$src" -o "${src%.dot}.png"
    echo "Creato $(pwd)/${src%.dot}.png"
done

python3 fasi-giorno.py
