"""Values you type into the web interface, kept in their own file (overrides.ui.csv).

Kept apart from your hand-written overrides.csv so the program never rewrites a file you edit
yourself. `taxdeed auto` applies both on every run, this one last, so a fresh download never
erases what you entered.
"""
from __future__ import annotations

import csv
import os
import tempfile
from pathlib import Path

BASE = ["parcel_id", "county"]


def _fmt(v) -> str:
    if isinstance(v, bool):
        return "Y" if v else "N"
    if isinstance(v, float) and v == int(v):
        return str(int(v))
    return str(v)


def load(path: str | Path) -> dict[tuple[str, str], dict[str, str]]:
    p = Path(path)
    if not p.exists():
        return {}
    with open(p, newline="", encoding="utf-8") as f:
        return {(r.get("county", ""), r["parcel_id"]): {k: v for k, v in r.items()
                                                         if k not in BASE and v not in (None, "")}
                for r in csv.DictReader(f) if r.get("parcel_id")}


def save_changes(path: str | Path, county: str, parcel_id: str, changes: dict) -> None:
    """Set each field to its value, or remove it where the value is None. Written atomically."""
    rows = load(path)
    row = rows.setdefault((county, parcel_id), {})
    for k, v in changes.items():
        if v is None or v == "":
            row.pop(k, None)
        else:
            row[k] = _fmt(v)
    rows = {k: r for k, r in rows.items() if r}
    fields = sorted({f for r in rows.values() for f in r})
    p = Path(path)
    fd, tmp = tempfile.mkstemp(dir=p.parent if str(p.parent) else ".", suffix=".tmp")
    with os.fdopen(fd, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=BASE + fields)
        w.writeheader()
        for (county_, pid), r in sorted(rows.items()):
            w.writerow({"parcel_id": pid, "county": county_, **r})
    os.replace(tmp, p)
