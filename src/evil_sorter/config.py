from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    host: str
    port: int
    evil_caiman_root: Path
    tachyon_mount: Path
    catalog: Path
    exclusion_registry: Path
    decision_database: Path
    downstream_selection: Path
    reviewer: str
    component_gate: str
    chunk_minutes: int
    auto_advance: bool


def load_settings(path: Path | None = None) -> Settings:
    source = path or ROOT / "config.json"
    raw = json.loads(source.read_text())
    if raw.get("component_gate") != "native_accepted":
        raise ValueError("This 2P viewer must use component_gate=native_accepted")
    return Settings(
        host=str(raw["host"]), port=int(raw["port"]),
        evil_caiman_root=Path(raw["evil_caiman_root"]),
        tachyon_mount=Path(raw["tachyon_mount"]), catalog=Path(raw["catalog"]),
        exclusion_registry=Path(raw["exclusion_registry"]),
        decision_database=Path(raw["decision_database"]),
        downstream_selection=Path(raw["downstream_selection"]),
        reviewer=str(raw.get("reviewer", "unknown")),
        component_gate=str(raw["component_gate"]),
        chunk_minutes=int(raw.get("chunk_minutes", 10)),
        auto_advance=bool(raw.get("auto_advance", True)),
    )

