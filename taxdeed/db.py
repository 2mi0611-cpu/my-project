"""Tiny SQLite store: one row per (county, parcel_id), parcel stored as JSON."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .models import Parcel

SCHEMA = """
CREATE TABLE IF NOT EXISTS parcels (
    county      TEXT NOT NULL,
    parcel_id   TEXT NOT NULL,
    sale_date   TEXT,
    data        TEXT NOT NULL,
    updated_at  TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (county, parcel_id)
);
"""


class Store:
    def __init__(self, path: str | Path = "taxdeed.db"):
        self.conn = sqlite3.connect(str(path))
        self.conn.execute(SCHEMA)

    def upsert(self, parcels: list[Parcel]) -> None:
        with self.conn:
            for p in parcels:
                self.conn.execute(
                    "INSERT INTO parcels (county, parcel_id, sale_date, data) VALUES (?, ?, ?, ?) "
                    "ON CONFLICT(county, parcel_id) DO UPDATE SET sale_date=excluded.sale_date, "
                    "data=excluded.data, updated_at=CURRENT_TIMESTAMP",
                    (p.county, p.parcel_id, p.sale_date, json.dumps(p.to_dict())),
                )

    def all(self, county: str | None = None) -> list[Parcel]:
        q, args = "SELECT data FROM parcels", ()
        if county:
            q, args = q + " WHERE county = ?", (county,)
        return [Parcel.from_dict(json.loads(r[0])) for r in self.conn.execute(q, args)]

    def close(self) -> None:
        self.conn.close()
