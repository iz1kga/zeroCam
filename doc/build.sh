#!/usr/bin/env bash
#
# Costruisce il manuale zeroCAM unendo i capitoli Markdown.
#
#   ./build.sh          -> zeroCAM-manuale.pdf
#   ./build.sh html     -> zeroCAM-manuale.html (utile se manca LaTeX)
#
set -euo pipefail
cd "$(dirname "$0")"

FORMAT="${1:-pdf}"
OUT="zeroCAM-manuale.$FORMAT"
CHAPTERS=( [0-9][0-9]-*.md )

if ! command -v pandoc >/dev/null; then
    echo "Serve pandoc:  sudo apt install pandoc" >&2
    exit 1
fi

# La versione finisce in copertina: il file VERSION contiene il tag installato,
# ma nel repository e' ancora il segnaposto di git-archive.
VERSION="$(cat ../VERSION 2>/dev/null || true)"
case "$VERSION" in
    *Format*|'') VERSION="$(git -C .. describe --tags --always 2>/dev/null || echo 'versione di sviluppo')" ;;
esac
# git describe da' 'v1.1.2-6-gabc1234': in copertina si legge meglio come
# tag piu' il numero di commit che lo seguono.
if [[ "$VERSION" =~ ^(.+)-([0-9]+)-g[0-9a-f]+$ ]]; then
    VERSION="${BASH_REMATCH[1]} (+${BASH_REMATCH[2]} commit)"
fi

OGGI="$(date '+%d/%m/%Y')"

COMMON=(
    --metadata-file=metadata.yaml
    --metadata "date=$OGGI"
    --metadata "subtitle=Manuale d'uso e di configurazione — $VERSION"
    --toc --toc-depth=2
    --number-sections
    --highlight-style=tango
    --from=markdown+pipe_tables+yaml_metadata_block
)

case "$FORMAT" in
    pdf)
        ENGINE=""
        for candidate in xelatex lualatex pdflatex; do
            command -v "$candidate" >/dev/null && { ENGINE="$candidate"; break; }
        done
        if [ -z "$ENGINE" ]; then
            echo "Nessun motore LaTeX trovato:  sudo apt install texlive-xetex texlive-fonts-recommended" >&2
            echo "In alternativa:  ./build.sh html" >&2
            exit 1
        fi
        # La copertina porta versione e data, quindi si rifa a ogni build
        python3 img/genera-copertina.py --versione "$VERSION" --data "$OGGI" >/dev/null
        pandoc "${COMMON[@]}" --pdf-engine="$ENGINE" \
               --include-in-header=copertina.tex \
               "${CHAPTERS[@]}" -o "$OUT"
        ;;
    html)
        pandoc "${COMMON[@]}" --standalone --embed-resources "${CHAPTERS[@]}" -o "$OUT"
        ;;
    *)
        echo "Formato non gestito: $FORMAT (usare pdf o html)" >&2
        exit 1
        ;;
esac

echo "Creato $(pwd)/$OUT"
