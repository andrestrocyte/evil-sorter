#!/bin/zsh
set -euo pipefail
EVIL_SORTER_ROOT="${0:A:h}"
cd "$EVIL_SORTER_ROOT"
export PYTHONPATH="$EVIL_SORTER_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
exec "${EVIL_SORTER_PYTHON:-python3}" -m evil_sorter
