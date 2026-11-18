from __future__ import annotations

import time

import requests

SESSION = requests.Session()
SESSION.headers["User-Agent"] = "taxdeed-screener/0.1"


def get_json(url: str, params: dict, retries: int = 3, timeout: int = 30) -> dict:
    """GET with simple retry/backoff. Raises on final failure."""
    last = None
    for attempt in range(retries):
        try:
            r = SESSION.get(url, params=params, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError) as e:
            last = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"Request failed after {retries} tries: {url}: {last}")


def arcgis_point_query(layer_url: str, lon: float, lat: float, out_fields: str) -> list[dict]:
    """Return attributes of every feature in an ArcGIS layer that contains the point."""
    data = get_json(
        f"{layer_url}/query",
        {
            "geometry": f"{lon},{lat}",
            "geometryType": "esriGeometryPoint",
            "inSR": 4326,
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": out_fields,
            "returnGeometry": "false",
            "f": "json",
        },
    )
    if "error" in data:
        raise RuntimeError(f"ArcGIS error from {layer_url}: {data['error']}")
    return [f.get("attributes", {}) for f in data.get("features", [])]
