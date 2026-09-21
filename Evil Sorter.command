#!/bin/zsh
set -euo pipefail
EVIL_SORTER_ROOT="${0:A:h}"
cd "$EVIL_SORTER_ROOT"
export PYTHONPATH="$EVIL_SORTER_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
sorter_python="${EVIL_SORTER_PYTHON:-$EVIL_SORTER_ROOT/../evil_caiman/.venv/bin/python}"
if [[ ! -x "$sorter_python" ]]; then
  sorter_python="${EVIL_SORTER_PYTHON:-python3}"
fi
exec "$sorter_python" -m evil_sorter
