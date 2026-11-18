"""Elevation and rough slope from the USGS Elevation Point Query Service.

Slope is estimated by sampling the parcel center and four points around it
(spaced by half the side of a square of the lot's area). It's a screening
number, not a survey.
"""
from __future__ import annotations

import math

from .http import get_json

URL = "https://epqs.nationalmap.gov/v1/json"
ACRE_M2 = 4046.86


def elevation_ft(lat: float, lon: float) -> float | None:
    data = get_json(URL, {"x": lon, "y": lat, "units": "Feet", "wkid": 4326})
    v = data.get("value")
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return None if v < -1000 else v  # EPQS returns -1000000 for no data


def _offset(lat: float, lon: float, dn_m: float, de_m: float) -> tuple[float, float]:
    dlat = dn_m / 111_320
    dlon = de_m / (111_320 * math.cos(math.radians(lat)))
    return lat + dlat, lon + dlon


def slope_pct(lat: float, lon: float, lot_acres: float | None, elev_fn=elevation_ft) -> tuple[float | None, float | None]:
    """Return (center_elevation_ft, max_slope_pct)."""
    center = elev_fn(lat, lon)
    if center is None:
        return None, None
    side_m = math.sqrt((lot_acres or 0.25) * ACRE_M2)
    run_m = max(side_m / 2, 10)
    run_ft = run_m * 3.28084
    worst = 0.0
    for dn, de in ((run_m, 0), (-run_m, 0), (0, run_m), (0, -run_m)):
        e = elev_fn(*_offset(lat, lon, dn, de))
        if e is not None:
            worst = max(worst, abs(e - center) / run_ft * 100)
    return center, round(worst, 1)
