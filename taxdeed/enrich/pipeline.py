"""Run every enrichment step on a parcel. Each step fails soft: an outage in one
service leaves that field empty (the scorer then marks the parcel REVIEW)."""
from __future__ import annotations

import logging

from ..models import Parcel
from . import elevation, flood, geocode, wetlands

log = logging.getLogger(__name__)


def enrich(p: Parcel) -> Parcel:
    if (p.lat is None or p.lon is None) and p.address:
        try:
            loc = geocode.geocode(f"{p.address}, {p.state}".strip(", "))
            if loc:
                p.lat, p.lon = loc
        except Exception as e:  # noqa: BLE001
            log.warning("geocode failed for %s: %s", p.parcel_id, e)

    if p.lat is not None and p.lon is not None:
        try:
            p.flood_zone, p.in_sfha = flood.flood_zone(p.lat, p.lon)
        except Exception as e:  # noqa: BLE001
            log.warning("flood lookup failed for %s: %s", p.parcel_id, e)
        try:
            p.wetlands, p.wetland_types = wetlands.wetlands(p.lat, p.lon)
        except Exception as e:  # noqa: BLE001
            log.warning("wetlands lookup failed for %s: %s", p.parcel_id, e)
        try:
            p.elevation_ft, p.slope_pct = elevation.slope_pct(p.lat, p.lon, p.lot_acres)
        except Exception as e:  # noqa: BLE001
            log.warning("elevation lookup failed for %s: %s", p.parcel_id, e)
    return p
