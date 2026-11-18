"""FEMA National Flood Hazard Layer lookup.

Zones starting with A or V are Special Flood Hazard Areas (the 1%-annual-chance
"100-year" floodplain): building there needs elevation, flood insurance, and
often is not economical. X / X500 / D are outside the SFHA.
"""
from __future__ import annotations

from .http import arcgis_point_query

# Layer 28 = "Flood Hazard Zones" in FEMA's public NFHL MapServer
LAYER = "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28"


def flood_zone(lat: float, lon: float) -> tuple[str | None, bool | None]:
    """Return (zone, in_sfha). (None, None) means FEMA has no mapped zone here."""
    feats = arcgis_point_query(LAYER, lon, lat, "FLD_ZONE,ZONE_SUBTY,SFHA_TF")
    if not feats:
        return None, None
    # If the point touches several polygons, report the worst one.
    zones = [(f.get("FLD_ZONE") or "", f.get("SFHA_TF") == "T") for f in feats]
    zones.sort(key=lambda z: not z[1])
    zone, sfha = zones[0]
    return zone, sfha or zone.upper().startswith(("A", "V"))
