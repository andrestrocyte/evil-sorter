#!/bin/zsh
set -euo pipefail
EVIL_SORTER_ROOT="/Users/deviandr/Documents/evil_sorter"
cd "$EVIL_SORTER_ROOT"
export PYTHONPATH="$EVIL_SORTER_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
exec /Users/deviandr/miniforge3/bin/python -m evil_sorter

