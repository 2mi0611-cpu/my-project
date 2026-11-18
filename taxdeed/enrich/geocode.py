"""Address -> lat/lon via the free U.S. Census geocoder.

Many vacant tax-deed lots have no street address; for those, put lat/lon in the
CSV directly (from the county GIS parcel viewer).
"""
from __future__ import annotations

from .http import get_json

URL = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"


def geocode(address: str) -> tuple[float, float] | None:
    if not address:
        return None
    data = get_json(URL, {"address": address, "benchmark": "Public_AR_Current", "format": "json"})
    matches = data.get("result", {}).get("addressMatches", [])
    if not matches:
        return None
    c = matches[0]["coordinates"]
    return float(c["y"]), float(c["x"])
