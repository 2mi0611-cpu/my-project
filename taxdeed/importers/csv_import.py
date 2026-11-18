"""Import any county's auction list from CSV.

Counties name their columns differently, so pass a column map, e.g.
    {"parcel_id": "Parcel Number", "opening_bid": "Opening Bid", ...}
Columns not in the map are matched by their normalized name (case/space-insensitive).
"""
from __future__ import annotations

import csv
import re

from ..models import Parcel

NUMERIC = {"opening_bid", "assessed_value", "lot_acres", "lot_width_ft", "lat", "lon",
           "building_sqft", "year_built", "bedrooms", "bathrooms", "code_violations",
           "est_arv", "est_rent"}
BOOLEAN = {"improved", "road_frontage", "occupied"}

# Common header spellings seen on auction lists -> our field names
ALIASES = {
    "parcel": "parcel_id", "parcel_number": "parcel_id", "parcel_no": "parcel_id",
    "apn": "parcel_id", "pin": "parcel_id", "folio": "parcel_id", "account": "parcel_id",
    "property_address": "address", "situs": "address", "situs_address": "address",
    "legal": "legal_description",
    "minimum_bid": "opening_bid", "min_bid": "opening_bid", "opening_bid_amount": "opening_bid",
    "assessed": "assessed_value", "just_value": "assessed_value", "market_value": "assessed_value",
    "acres": "lot_acres", "acreage": "lot_acres",
    "lot_width": "lot_width_ft", "width": "lot_width_ft", "frontage_ft": "lot_width_ft",
    # non-auction distressed lists (pre-foreclosure, probate, wholesaler): price = what you'd pay
    "price": "opening_bid", "asking_price": "opening_bid", "list_price": "opening_bid",
    "owner": "owner_name",
    "sqft": "building_sqft", "living_area": "building_sqft", "heated_area": "building_sqft",
    "bldg_sqft": "building_sqft", "living_sqft": "building_sqft", "square_feet": "building_sqft",
    "yr_built": "year_built", "built": "year_built",
    "beds": "bedrooms", "baths": "bathrooms",
    "cond": "condition", "building_condition": "condition",
    "occupancy": "occupied", "violations": "code_violations",
    "arv": "est_arv", "after_repair_value": "est_arv",
    "rent": "est_rent", "market_rent": "est_rent",
    "latitude": "lat", "longitude": "lon", "lng": "lon",
}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.strip().lower()).strip("_")


def _num(v: str):
    v = (v or "").strip().replace("$", "").replace(",", "")
    if not v:
        return None
    try:
        return float(v)
    except ValueError:
        return None


def _bool(v: str):
    v = (v or "").strip().lower()
    if v in {"y", "yes", "true", "1", "improved", "occupied"}:
        return True
    if v in {"n", "no", "false", "0", "vacant"}:
        return False
    return None


def import_csv(path: str, county: str = "", state: str = "",
               column_map: dict[str, str] | None = None) -> list[Parcel]:
    column_map = column_map or {}
    reverse = {src: dst for dst, src in column_map.items()}
    fields = set(Parcel.__dataclass_fields__)
    parcels = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            rec: dict = {}
            for header, value in row.items():
                if header is None:
                    continue
                key = reverse.get(header) or ALIASES.get(_norm(header)) or _norm(header)
                if key not in fields:
                    continue
                if key in NUMERIC:
                    rec[key] = _num(value)
                elif key in BOOLEAN:
                    rec[key] = _bool(value)
                else:
                    rec[key] = (value or "").strip()
            if not rec.get("parcel_id"):
                continue
            rec.setdefault("county", county)
            rec.setdefault("state", state)
            if not rec["county"]:
                rec["county"] = county
            if not rec["state"]:
                rec["state"] = state
            parcels.append(Parcel(**rec))
    return parcels
