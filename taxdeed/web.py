"""Local web interface: browse, filter and re-score the properties in the database.

Standard library only. Binds to 127.0.0.1 by default so only this computer can reach it.
Reads taxdeed.db; saves your edits to overrides.ui.csv and re-scores the property at once.
"""
from __future__ import annotations

import json
import math
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from . import overrides
from .db import Store
from .models import Parcel
from .scoring import score

STATIC = Path(__file__).parent / "static"
FILES = {"/": ("index.html", "text/html; charset=utf-8"),
         "/app.js": ("app.js", "text/javascript; charset=utf-8"),
         "/app.css": ("app.css", "text/css; charset=utf-8")}

NUMBER_FIELDS = {"assessed_value": 1e10, "est_market_value": 1e10, "est_arv": 1e10, "est_rent": 1e6,
                 "lot_acres": 1e5, "lot_width_ft": 1e5, "building_sqft": 1e6, "bedrooms": 100,
                 "bathrooms": 100, "code_violations": 10000}
BOOL_FIELDS = {"improved", "occupied", "road_frontage"}
TEXT_FIELDS = {"condition": 60, "zoning": 30, "land_use": 80, "address": 120}
MAX_BODY = 64 * 1024


def clean_changes(changes: object) -> dict:
    """Validate what the browser sent. Raises ValueError with a message safe to show the user."""
    if not isinstance(changes, dict) or not changes:
        raise ValueError("nothing to save")
    out: dict = {}
    for k, v in changes.items():
        if k in NUMBER_FIELDS:
            if v is None or v == "":
                out[k] = None
                continue
            try:
                n = float(v)
            except (TypeError, ValueError):
                raise ValueError(f"{k}: not a number") from None
            if isinstance(v, bool) or not math.isfinite(n) or n < 0 or n > NUMBER_FIELDS[k]:
                raise ValueError(f"{k}: out of range")
            out[k] = n
        elif k == "year_built":
            if v is None or v == "":
                out[k] = None
                continue
            try:
                n = int(float(v))
            except (TypeError, ValueError):
                raise ValueError("year_built: not a number") from None
            if not 1700 <= n <= 2100:
                raise ValueError("year_built: out of range")
            out[k] = float(n)
        elif k in BOOL_FIELDS:
            if v is not None and not isinstance(v, bool):
                raise ValueError(f"{k}: must be yes, no or unknown")
            out[k] = v
        elif k in TEXT_FIELDS:
            if v is not None and not isinstance(v, str):
                raise ValueError(f"{k}: must be text")
            v = (v or "").strip()
            if len(v) > TEXT_FIELDS[k]:
                raise ValueError(f"{k}: too long")
            out[k] = v or None
        else:
            raise ValueError(f"{k}: this field can't be edited")
    return out


def payload(p: Parcel) -> dict:
    d = p.to_dict()
    d["key"] = f"{p.county}|{p.parcel_id}"
    d["needs_data"] = p.est_market_value is None and p.est_arv is None
    return d


class App:
    def __init__(self, db_path, cfg, overrides_path):
        self.db_path, self.cfg, self.overrides_path = str(db_path), cfg, str(overrides_path)
        self.lock = threading.Lock()   # one writer at a time for the database + overrides file

    def list_parcels(self) -> dict:
        store = Store(self.db_path)
        try:
            parcels = [payload(p) for p in store.all()]
        finally:
            store.close()
        return {"parcels": parcels, "min_score": self.cfg["automation"]["min_score"]}

    def edit(self, county: str, parcel_id: str, raw_changes: object) -> dict | None:
        changes = clean_changes(raw_changes)
        with self.lock:
            store = Store(self.db_path)
            try:
                p = store.get(county, parcel_id)
                if p is None:
                    return None
                stale_arv = any(n.startswith("ARV taken from assessed") for n in p.notes)
                for k, v in changes.items():
                    setattr(p, k, ("" if k in TEXT_FIELDS else None) if v is None else v)
                # Values the scorer derived earlier must be rebuilt from what you just entered.
                if "est_market_value" not in changes and "assessed_value" in changes:
                    p.est_market_value = None
                if "est_arv" not in changes and stale_arv and (
                        "assessed_value" in changes or "est_market_value" in changes):
                    p.est_arv = None
                score(p, self.cfg)
                store.upsert([p])
                overrides.save_changes(self.overrides_path, county, parcel_id, changes)
                return payload(p)
            finally:
                store.close()


class Handler(BaseHTTPRequestHandler):
    server_version = "taxdeed"

    def log_message(self, *args):  # keep the terminal quiet
        pass

    @property
    def app(self) -> App:
        return self.server.app  # type: ignore[attr-defined]

    def _send(self, status: int, body: bytes, ctype: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; img-src 'self' data:; base-uri 'none'; form-action 'none'")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, obj: object) -> None:
        self._send(status, json.dumps(obj).encode(), "application/json")

    def do_GET(self):  # noqa: N802
        path = urlparse(self.path).path
        if path in FILES:
            name, ctype = FILES[path]
            self._send(200, (STATIC / name).read_bytes(), ctype)
        elif path == "/api/parcels":
            self._json(200, self.app.list_parcels())
        elif path == "/favicon.ico":
            self._send(204, b"", "image/x-icon")
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):  # noqa: N802
        if urlparse(self.path).path != "/api/edit":
            return self._json(404, {"error": "not found"})
        # A custom header plus a JSON body can't be sent by another website's page without a
        # CORS preflight, which this server never grants: that blocks cross-site edits.
        if self.headers.get("X-Taxdeed") != "1" or \
                not (self.headers.get("Content-Type") or "").startswith("application/json"):
            return self._json(403, {"error": "forbidden"})
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        if not 0 < length <= MAX_BODY:
            return self._json(400, {"error": "bad request size"})
        try:
            body = json.loads(self.rfile.read(length))
            county, parcel_id = body["county"], body["parcel_id"]
            if not isinstance(county, str) or not isinstance(parcel_id, str):
                raise ValueError("bad id")
            result = self.app.edit(county, parcel_id, body.get("changes"))
        except (ValueError, KeyError, TypeError) as e:
            return self._json(400, {"error": str(e) or "bad request"})
        if result is None:
            return self._json(404, {"error": "property not found"})
        self._json(200, result)


def make_server(db_path, cfg, overrides_path="overrides.ui.csv", host="127.0.0.1", port=8765):
    srv = ThreadingHTTPServer((host, port), Handler)
    srv.app = App(db_path, cfg, overrides_path)  # type: ignore[attr-defined]
    return srv
