"""U.S. Fish & Wildlife Service National Wetlands Inventory lookup.

A hit here is a strong warning, not a final answer: NWI maps are approximate,
and only a field delineation decides what is legally a wetland.
"""
from __future__ import annotations

from .http import arcgis_point_query

LAYER = "https://fwspublicservices.wim.usgs.gov/wetlandsmapservice/rest/services/Wetlands/MapServer/0"


def wetlands(lat: float, lon: float) -> tuple[bool, str]:
    feats = arcgis_point_query(LAYER, lon, lat, "WETLAND_TYPE,ATTRIBUTE")
    types = sorted({f.get("WETLAND_TYPE") or f.get("ATTRIBUTE") or "unknown" for f in feats})
    return bool(feats), ", ".join(types)
