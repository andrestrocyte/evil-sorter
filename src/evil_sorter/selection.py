from __future__ import annotations

import hashlib
import json
from pathlib import Path


def load_manual_keep(path: Path, run_id: str, *, require_complete: bool = True) -> list[int]:
    """Return manually kept native IDs with an explicit completeness guard."""
    payload = json.loads(path.read_text())
    if payload.get("selection_gate") != "evil_sorter_manual_keep":
        raise ValueError("not an Evil Sorter manual-keep selection")
    run = payload.get("runs", {}).get(run_id)
    if run is None:
        raise KeyError(f"run has not been reviewed: {run_id}")
    if require_complete and not bool(run.get("review_complete")):
        raise RuntimeError(f"manual review is incomplete for {run_id}")
    keep = [int(x) for x in run["manual_keep_component_ids"]]
    native = {int(x) for x in run["native_accepted_component_ids"]}
    if not set(keep).issubset(native):
        raise ValueError("manual keep set is not a subset of native accepted")
    return keep

