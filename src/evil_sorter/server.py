from __future__ import annotations

import argparse
import json
import mimetypes
import traceback
import webbrowser
from threading import RLock
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .config import ROOT, load_settings
from .data import EvilData
from .store import DecisionStore


class App:
    def __init__(self, config: Path | None = None):
        self.settings = load_settings(config)
        self.store = DecisionStore(self.settings.decision_database)
        self.data = EvilData(self.settings, self.store)
        self.static = ROOT / "static"
        self.save_lock = RLock()


APP: App


class Handler(BaseHTTPRequestHandler):
    server_version = "EvilSorter/0.1"

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"[evil-sorter] {self.address_string()} {fmt % args}")

    def do_GET(self) -> None:
        try:
            parsed = urlparse(self.path)
            q = parse_qs(parsed.query)
            if parsed.path == "/api/health":
                return self.json({"ok": True, "version": "0.1.0"})
            if parsed.path == "/api/catalog":
                return self.json(APP.data.catalog())
            if parsed.path == "/api/run":
                info = APP.data.refresh_run_decisions(APP.data.run_info(required(q, "run_id")))
                return self.json(info)
            if parsed.path == "/api/component":
                data = APP.data.component(required(q, "run_id"), int(required(q, "component_id")),
                                          float(q.get("chunk_start_s", [0])[0]))
                return self.json(data)
            if parsed.path == "/api/fov":
                png = APP.data.fov_png(required(q, "run_id"), int(required(q, "component_id")),
                                       q.get("background", ["average"])[0])
                return self.bytes(png, "image/png", {"Cache-Control": "private, max-age=86400"})
            if parsed.path == "/api/export.csv":
                return self.bytes(APP.store.csv_bytes(), "text/csv; charset=utf-8",
                                  {"Content-Disposition": "attachment; filename=evil_sorter_decisions.csv"})
            if parsed.path == "/api/export.json":
                with APP.save_lock:
                    payload = APP.data.export_selection()
                return self.bytes((json.dumps(payload, indent=2) + "\n").encode(), "application/json",
                                  {"Content-Disposition": "attachment; filename=evil_sorter_selection.json"})
            return self.static_file(parsed.path)
        except Exception as exc:
            traceback.print_exc()
            self.json({"error": str(exc), "type": type(exc).__name__}, HTTPStatus.BAD_REQUEST)

    def do_POST(self) -> None:
        try:
            parsed = urlparse(self.path)
            if parsed.path != "/api/decision":
                return self.json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length) or b"{}")
            run_id = str(body["run_id"]); component_id = int(body["component_id"])
            info = APP.data.run_info(run_id)
            valid = {x["component_id"] for x in info["components"]}
            if component_id not in valid:
                raise ValueError("decision target is not native accepted")
            # Serialize the database/export pair, including concurrent browser tabs.
            with APP.save_lock:
                row = APP.store.put(info["row"]["analysis_id"], run_id, component_id,
                                    str(body["decision"]), APP.settings.reviewer, str(body.get("note", "")))
                exported = APP.data.export_selection()
            return self.json({"saved": row, "selection_sha256": exported["selection_sha256"]})
        except Exception as exc:
            traceback.print_exc()
            self.json({"error": str(exc), "type": type(exc).__name__}, HTTPStatus.BAD_REQUEST)

    def static_file(self, request_path: str) -> None:
        rel = "index.html" if request_path in {"", "/"} else request_path.lstrip("/")
        target = (APP.static / rel).resolve()
        if APP.static.resolve() not in target.parents and target != APP.static.resolve():
            return self.json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        if not target.exists() or not target.is_file():
            return self.json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        self.bytes(target.read_bytes(), mimetypes.guess_type(target.name)[0] or "application/octet-stream")

    def json(self, payload: object, status: int = 200) -> None:
        self.bytes((json.dumps(payload, separators=(",", ":"), allow_nan=False) + "\n").encode(),
                   "application/json; charset=utf-8", status=status)

    def bytes(self, payload: bytes, content_type: str, headers: dict[str, str] | None = None,
              status: int = 200) -> None:
        self.send_response(status); self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        if "Cache-Control" not in (headers or {}):
            self.send_header("Cache-Control", "no-store")
        for key, value in (headers or {}).items(): self.send_header(key, value)
        self.end_headers()
        try:
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError):
            pass  # Navigation may cancel an obsolete read.


def required(query: dict[str, list[str]], key: str) -> str:
    if key not in query or not query[key]: raise ValueError(f"missing query parameter: {key}")
    return query[key][0]


def main() -> None:
    parser = argparse.ArgumentParser(description="Evil Sorter manual component viewer")
    parser.add_argument("--config", type=Path); parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    global APP
    APP = App(args.config)
    address = (APP.settings.host, APP.settings.port)
    url = f"http://{address[0]}:{address[1]}"
    print(f"Evil Sorter ready at {url}")
    print(f"Decisions: {APP.settings.decision_database}")
    print(f"Downstream selection: {APP.settings.downstream_selection}")
    if not args.no_browser: webbrowser.open(url)
    ThreadingHTTPServer(address, Handler).serve_forever()


if __name__ == "__main__": main()
