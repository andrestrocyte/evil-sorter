from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import h5py
import numpy as np
from PIL import Image
from scipy import ndimage, sparse

from .config import Settings
from .store import DecisionStore, atomic_json, sha256_file, utc_now


def minmax_decimate(y: np.ndarray, start: int, stop: int, points: int) -> tuple[np.ndarray, np.ndarray]:
    start, stop = max(0, int(start)), min(len(y), int(stop))
    if stop <= start:
        return np.array([], dtype=int), np.array([], dtype=float)
    n = stop - start
    if n <= points:
        idx = np.arange(start, stop, dtype=int)
        return idx, np.asarray(y[start:stop], dtype=float)
    bins = max(2, points // 2)
    edges = np.linspace(start, stop, bins + 1, dtype=int)
    chosen: list[int] = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        chunk = np.asarray(y[lo:hi])
        finite = np.flatnonzero(np.isfinite(chunk))
        if not len(finite):
            continue
        a = lo + int(finite[np.argmin(chunk[finite])])
        b = lo + int(finite[np.argmax(chunk[finite])])
        chosen.extend(sorted({a, b}))
    idx = np.asarray(chosen, dtype=int)
    return idx, np.asarray(y[idx], dtype=float)


class EvilData:
    def __init__(self, settings: Settings, store: DecisionStore):
        self.settings, self.store = settings, store
        self.excluded = self._load_exclusions()
        self.rows = self._load_catalog()
        self.by_run = {row["run_id"]: row for row in self.rows}

    def _load_exclusions(self) -> set[str]:
        raw = json.loads(self.settings.exclusion_registry.read_text())
        return {str(x["mouse_id"]) for x in raw.get("exclusions", [])
                if x.get("scope") == "all_future_quantitative_valence_analyses"}

    def _load_catalog(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        with self.settings.catalog.open(newline="") as handle:
            for raw in csv.DictReader(handle):
                if raw["mouse_id"] in self.excluded:
                    continue
                row = dict(raw)
                for key in ("session_id", "frame_count", "n_native_accepted", "n_soma_valid"):
                    row[key] = int(row[key])
                row["duration_s"] = float(row["duration_s"])
                rows.append(row)
        rows.sort(key=lambda x: ({"AM": 0, "AL": 1, "PM": 2}.get(x["group"], 9), x["mouse_id"], x["session_id"]))
        return rows

    def catalog(self) -> dict[str, Any]:
        groups: dict[str, dict[str, list[dict[str, Any]]]] = {}
        all_decisions = {r["run_id"]: self.store.get_run(r["run_id"]) for r in self.rows}
        for row in self.rows:
            decisions = all_decisions[row["run_id"]]
            groups.setdefault(row["group"], {}).setdefault(row["mouse_id"], []).append({
                "session": row["session_id"], "run_id": row["run_id"],
                "n_native": row["n_native_accepted"], "reviewed": len(decisions),
                "kept": sum(d["decision"] == "keep" for d in decisions.values()),
                "rejected": sum(d["decision"] == "reject" for d in decisions.values()),
                "duration_s": row["duration_s"],
            })
        return {"groups": groups, "excluded_mice": sorted(self.excluded),
                "component_gate": "native_accepted", "chunk_minutes": self.settings.chunk_minutes,
                "auto_advance": self.settings.auto_advance}

    def run_dir(self, run_id: str) -> Path:
        row = self.by_run.get(run_id)
        if row is None:
            raise KeyError(f"unknown or excluded run_id: {run_id}")
        path = self.settings.tachyon_mount / row["analysis_id"] / "runs" / run_id
        if not (path / "cnmf/_SUCCESS").exists() or not (path / "report/_SUCCESS").exists():
            raise RuntimeError(f"run is not closed: {path}")
        return path

    @lru_cache(maxsize=16)
    def run_info(self, run_id: str) -> dict[str, Any]:
        row = self.by_run[run_id]
        path = self.run_dir(run_id)
        audit = json.loads((path / "report/component_audit.json").read_text())
        native_rows = [x for x in audit["components"] if bool(x.get("native_accepted"))]
        native_rows.sort(key=lambda x: int(x["component_id"]))
        decisions = self.store.get_run(run_id)
        components = []
        for x in native_rows:
            component_id = int(x["component_id"])
            components.append({
                "component_id": component_id,
                "soma_valid": bool(x.get("soma_valid")),
                "snr": _number(x.get("snr")), "r_value": _number(x.get("r_value")),
                "cnn": _number(x.get("cnn_probability", x.get("cnn_pred"))),
                "decision": decisions.get(component_id, {}).get("decision", "pending"),
            })
        if len(components) != row["n_native_accepted"]:
            raise RuntimeError(f"native component count mismatch for {run_id}")
        params = json.loads((path / "cnmf/resolved_caiman_params.json").read_text())
        frame_rate = float(params["data"]["fr"])
        return {"row": row, "components": components, "frame_rate": frame_rate,
                "duration_s": row["frame_count"] / frame_rate, "run_path": str(path)}

    def refresh_run_decisions(self, info: dict[str, Any]) -> dict[str, Any]:
        decisions = self.store.get_run(info["row"]["run_id"])
        clone = {**info, "components": [dict(x) for x in info["components"]]}
        for x in clone["components"]:
            x["decision"] = decisions.get(x["component_id"], {}).get("decision", "pending")
        return clone

    def component(self, run_id: str, component_id: int, chunk_start_s: float) -> dict[str, Any]:
        info = self.run_info(run_id)
        valid = {x["component_id"] for x in info["components"]}
        if component_id not in valid:
            raise KeyError(f"component {component_id} is not native accepted")
        traces = self.trace_data(run_id, component_id)
        fr = float(info["frame_rate"]); n = len(traces["F_dff"])
        chunk_frames = int(self.settings.chunk_minutes * 60 * fr)
        chunk_start = min(max(0, int(float(chunk_start_s) * fr)), max(0, n - 1))
        chunk_stop = min(n, chunk_start + chunk_frames)
        payload: dict[str, Any] = {"component_id": component_id, "frame_rate": fr,
                                  "duration_s": n / fr, "chunk_start_s": chunk_start / fr,
                                  "chunk_stop_s": chunk_stop / fr, "signals": {}}
        for name, y in traces.items():
            oi, ov = minmax_decimate(y, 0, n, 5000)
            ci, cv = minmax_decimate(y, chunk_start, chunk_stop, 8000)
            payload["signals"][name] = {
                "whole_t": (oi / fr).round(4).tolist(), "whole_y": ov.round(6).tolist(),
                "chunk_t": (ci / fr).round(4).tolist(), "chunk_y": cv.round(6).tolist(),
                "whole_range": finite_range(y), "chunk_range": finite_range(y[chunk_start:chunk_stop]),
            }
        return payload

    @lru_cache(maxsize=128)
    def trace_data(self, run_id: str, component_id: int) -> dict[str, np.ndarray]:
        """Load a component once; later chunk changes and revisits are memory-speed."""
        path = self.run_dir(run_id) / "cnmf/cnmf_final.hdf5"
        with h5py.File(path, "r") as h5:
            return {name: np.asarray(h5[f"estimates/{name}"][component_id], dtype=np.float32)
                    for name in ("F_dff", "C", "S")}

    @lru_cache(maxsize=128)
    def fov_png(self, run_id: str, component_id: int, background: str = "average") -> bytes:
        info = self.run_info(run_id)
        native = [x["component_id"] for x in info["components"]]
        if component_id not in native:
            raise KeyError(f"component {component_id} is not native accepted")
        run = self.run_dir(run_id)
        summaries = np.load(run / "motion_correction/summary_images.npz")
        key = {"average": "average_image", "correlation": "correlation_image", "max": "max_image"}.get(background, "average_image")
        image = np.asarray(summaries[key], dtype=float)
        matrix, dims, union = self.spatial_data(run_id)
        selected = np.asarray(matrix[:, component_id].toarray()).ravel().reshape(dims, order="F")
        rgb = normalize_gray(image)
        all_edge = union ^ ndimage.binary_erosion(union)
        selected_mask = selected >= np.nanmax(selected) * 0.22
        selected_edge = ndimage.binary_dilation(selected_mask, iterations=2) ^ ndimage.binary_erosion(selected_mask, iterations=1)
        rgb[all_edge] = np.array([150, 144, 165], dtype=np.uint8)
        alpha = np.clip(selected / max(float(np.nanmax(selected)), 1e-12), 0, 1)[..., None]
        tint = np.array([145, 45, 245], dtype=float)
        rgb = (rgb * (1 - 0.34 * alpha) + tint * (0.34 * alpha)).astype(np.uint8)
        rgb[selected_edge] = np.array([185, 255, 72], dtype=np.uint8)
        out = io.BytesIO(); Image.fromarray(rgb).save(out, format="PNG", optimize=False)
        return out.getvalue()

    @lru_cache(maxsize=8)
    def spatial_data(self, run_id: str) -> tuple[sparse.csc_matrix, tuple[int, int], np.ndarray]:
        """Cache immutable spatial footprints and the native-component union per run."""
        info = self.run_info(run_id)
        native = [x["component_id"] for x in info["components"]]
        run = self.run_dir(run_id)
        with h5py.File(run / "cnmf/cnmf_final.hdf5", "r") as h5:
            group = h5["estimates/A"]
            matrix = sparse.csc_matrix((group["data"][:], group["indices"][:], group["indptr"][:]),
                                       shape=tuple(int(x) for x in group["shape"][:]))
            dims = tuple(int(x) for x in h5["dims"][:])
        union = np.zeros(dims, dtype=bool)
        for cid in native:
            footprint = np.asarray(matrix[:, cid].toarray()).ravel().reshape(dims, order="F")
            peak = float(np.nanmax(footprint))
            if peak > 0:
                union |= footprint >= peak * 0.22
        return matrix, dims, union

    def export_selection(self) -> dict[str, Any]:
        decisions = self.store.all()
        decisions_by_run: dict[str, list[dict[str, Any]]] = {}
        for decision in decisions:
            decisions_by_run.setdefault(decision["run_id"], []).append(decision)
        by_run: dict[str, dict[str, Any]] = {}
        for row in self.rows:
            selected = decisions_by_run.get(row["run_id"], [])
            if not selected:
                continue
            info = self.run_info(row["run_id"])
            native = [x["component_id"] for x in info["components"]]
            keep = sorted(int(d["component_id"]) for d in selected if d["decision"] == "keep")
            reject = sorted(int(d["component_id"]) for d in selected if d["decision"] == "reject")
            reviewed = set(keep + reject)
            by_run[row["run_id"]] = {
                "analysis_id": row["analysis_id"], "group": row["group"], "mouse_id": row["mouse_id"],
                "session_id": row["session_id"], "variant": row["variant"],
                "native_accepted_component_ids": native,
                "manual_keep_component_ids": keep, "manual_reject_component_ids": reject,
                "pending_component_ids": [x for x in native if x not in reviewed],
                "review_complete": len(reviewed) == len(native),
            }
        payload: dict[str, Any] = {
            "schema_version": 1, "selection_name": "evil_sorter_valence_native_v1",
            "selection_gate": "evil_sorter_manual_keep", "review_universe": "native_accepted",
            "generated_at": utc_now(), "reviewer": self.settings.reviewer,
            "source_catalog": str(self.settings.catalog),
            "source_catalog_sha256": sha256_file(self.settings.catalog),
            "exclusion_registry": str(self.settings.exclusion_registry),
            "exclusion_registry_sha256": sha256_file(self.settings.exclusion_registry),
            "excluded_mice": sorted(self.excluded), "runs": by_run,
            "unreviewed_runs": [
                {"analysis_id": row["analysis_id"], "run_id": row["run_id"],
                 "group": row["group"], "mouse_id": row["mouse_id"],
                 "session_id": row["session_id"], "n_native_accepted": row["n_native_accepted"]}
                for row in self.rows if row["run_id"] not in decisions_by_run
            ],
        }
        digest_source = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        payload["selection_sha256"] = hashlib.sha256(digest_source).hexdigest()
        atomic_json(self.settings.downstream_selection, payload)
        return payload


def _number(value: Any) -> float | None:
    try:
        number = float(value)
        return number if np.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def finite_range(y: np.ndarray) -> list[float]:
    finite = np.asarray(y)[np.isfinite(y)]
    return [float(np.min(finite)), float(np.max(finite))] if len(finite) else [0.0, 1.0]


def normalize_gray(image: np.ndarray) -> np.ndarray:
    finite = image[np.isfinite(image)]
    lo, hi = np.percentile(finite, [1, 99.7]) if len(finite) else (0.0, 1.0)
    scaled = np.clip((image - lo) / max(float(hi - lo), 1e-12), 0, 1)
    gray = (scaled * 255).astype(np.uint8)
    return np.repeat(gray[..., None], 3, axis=2)
