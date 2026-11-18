from __future__ import annotations

from pathlib import Path

import yaml

DEFAULTS: dict = {
    "buildable": {
        "min_lot_acres": 0.17,          # ~7,500 sq ft
        "min_lot_width_ft": 50,
        "max_slope_pct": 15,
        "allow_sfha": False,            # FEMA high-risk flood zones (A*, V*)
        "allow_wetlands": False,
        "require_road_frontage": True,
        "require_vacant": False,
        "allowed_zoning": [],           # empty = don't check zoning
    },
    "value": {
        "closing_costs": 1500,          # recording, title search, etc.
        "quiet_title_cost": 2500,       # many tax deeds need quiet title to be insurable
        "assessed_to_market_ratio": 1.0,  # if county assesses at e.g. 80% of market, use 0.8
        "max_bid_to_value": 0.6,        # skip deals where bid > 60% of value
    },
    "red_flag_keywords": [
        "common area", "common element", "drainage", "retention", "detention",
        "easement", "ingress", "egress", "strip", "sliver", "right of way",
        "r/w", "hoa", "cemetery", "pond", "canal", "landlocked", "undivided",
        "mineral", "subsurface", "submerged",
    ],
}


def _merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(path: str | Path | None = None) -> dict:
    if path is None:
        return _merge(DEFAULTS, {})
    with open(path) as f:
        return _merge(DEFAULTS, yaml.safe_load(f) or {})
