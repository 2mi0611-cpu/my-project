"""The automatic run: fetch every source -> import -> screen -> enrich survivors -> shortlist."""
from __future__ import annotations

import datetime as dt
import logging
from pathlib import Path

from .db import Store
from .enrich.pipeline import enrich
from .fetch import fetch_source, load_sources
from .importers.csv_import import import_csv, read_overrides
from .models import Parcel
from .report import write_csv, write_html
from .scoring import score

log = logging.getLogger(__name__)

# Looked-up data that is kept between runs so each property is only looked up once.
KEEP_FIELDS = ["lat", "lon", "flood_zone", "in_sfha", "wetlands", "wetland_types",
               "elevation_ft", "slope_pct"]


def _key(p: Parcel) -> tuple[str, str]:
    return (p.county, p.parcel_id)


def apply_overrides(parcels: list[Parcel], overrides: list[dict]) -> int:
    """Copy your own figures (ARV, rent, condition...) onto matching parcels. Returns match count."""
    applied = 0
    for rec in overrides:
        for p in parcels:
            if p.parcel_id != rec["parcel_id"]:
                continue
            if rec.get("county") and rec["county"].lower() != p.county.lower():
                continue
            for k, v in rec.items():
                if k not in ("parcel_id", "county", "state") and v not in (None, ""):
                    setattr(p, k, v)
            applied += 1
    return applied


def run(cfg: dict, store: Store, sources_path: str = "sources.yaml",
        overrides_path: str | None = "overrides.csv", out_root: str | None = None,
        only: list[str] | None = None, skip_enrich: bool = False,
        raw_dir: str = "data/raw", today: dt.date | None = None) -> dict:
    today = today or dt.date.today()
    auto = cfg["automation"]
    out_dir = Path(out_root or auto["output_dir"]) / today.isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)

    known = {_key(p): p for p in store.all()}
    current: list[Parcel] = []
    errors: dict[str, str] = {}
    sources_ok = 0

    for src in load_sources(sources_path):
        if only and src["name"] not in only:
            continue
        try:
            csv_path = fetch_source(src, raw_dir, today)
            parcels = import_csv(str(csv_path), county=src.get("county", ""),
                                 state=src.get("state", ""), column_map=src.get("map"))
            if not parcels:
                raise RuntimeError("no rows with a parcel id - check the `map:` for this source")
        except Exception as e:  # noqa: BLE001  one bad source must not stop the others
            log.warning("source %s failed: %s", src["name"], e)
            errors[src["name"]] = str(e)
            continue
        sources_ok += 1
        for p in parcels:
            p.source = src["name"]
            old = known.get(_key(p))
            p.is_new = old is None
            if old:
                for f in KEEP_FIELDS:
                    if getattr(p, f) in (None, "") and getattr(old, f) not in (None, ""):
                        setattr(p, f, getattr(old, f))
        current.extend(parcels)

    if overrides_path and Path(overrides_path).exists():
        apply_overrides(current, read_overrides(overrides_path))

    # Screen on list data first; only spend lookups on properties that haven't already failed.
    for p in current:
        score(p, cfg)
    if not skip_enrich:
        for p in current:
            if p.status != "FAIL" and p.flood_zone is None:
                enrich(p)
        for p in current:
            score(p, cfg)

    store.upsert(current)

    ranked = sorted(current, key=lambda p: p.deal_score or 0, reverse=True)
    shortlist = [p for p in ranked
                 if p.status in auto["shortlist_statuses"] and (p.deal_score or 0) >= auto["min_score"]
                 ][: auto["top_n"]]
    write_html(shortlist, str(out_dir / "shortlist.html"))
    write_csv(shortlist, str(out_dir / "shortlist.csv"))
    write_html(ranked, str(out_dir / "all.html"))
    write_csv(ranked, str(out_dir / "all.csv"))

    return {"out_dir": str(out_dir), "total": len(current), "new": sum(p.is_new for p in current),
            "sources_ok": sources_ok, "shortlist": shortlist, "errors": errors}
