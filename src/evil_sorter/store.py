from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS decisions (
  analysis_id TEXT NOT NULL,
  run_id TEXT NOT NULL,
  component_id INTEGER NOT NULL,
  decision TEXT NOT NULL CHECK(decision IN ('keep','reject')),
  reviewer TEXT NOT NULL,
  note TEXT NOT NULL DEFAULT '',
  updated_at TEXT NOT NULL,
  PRIMARY KEY (run_id, component_id)
);
CREATE INDEX IF NOT EXISTS decisions_analysis_run ON decisions(analysis_id, run_id);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class DecisionStore:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript(SCHEMA)

    def connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    def put(self, analysis_id: str, run_id: str, component_id: int,
            decision: str, reviewer: str, note: str = "") -> dict[str, Any]:
        if decision not in {"keep", "reject"}:
            raise ValueError("decision must be keep or reject")
        stamp = utc_now()
        with self.connect() as db:
            db.execute(
                """INSERT INTO decisions VALUES(?,?,?,?,?,?,?)
                   ON CONFLICT(run_id,component_id) DO UPDATE SET
                   analysis_id=excluded.analysis_id, decision=excluded.decision,
                   reviewer=excluded.reviewer, note=excluded.note,
                   updated_at=excluded.updated_at""",
                (analysis_id, run_id, int(component_id), decision, reviewer, note, stamp),
            )
        return {"analysis_id": analysis_id, "run_id": run_id,
                "component_id": int(component_id), "decision": decision,
                "reviewer": reviewer, "note": note, "updated_at": stamp}

    def get_run(self, run_id: str) -> dict[int, dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM decisions WHERE run_id=? ORDER BY component_id", (run_id,)
            ).fetchall()
        return {int(row["component_id"]): dict(row) for row in rows}

    def all(self) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM decisions ORDER BY analysis_id,run_id,component_id"
            ).fetchall()
        return [dict(row) for row in rows]

    def csv_bytes(self) -> bytes:
        rows = self.all()
        out = io.StringIO()
        fields = ["analysis_id", "run_id", "component_id", "decision", "reviewer", "note", "updated_at"]
        writer = csv.DictWriter(out, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)
        return out.getvalue().encode()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("wb") as handle:
        handle.write(raw); handle.flush(); os.fsync(handle.fileno())
    os.replace(temporary, path)

