from __future__ import annotations

from pathlib import Path

import yaml

DEFAULTS: dict = {
    # --- vacant land you want to build on ---
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
    # --- costs that apply to every purchase ---
    "value": {
        "closing_costs": 1500,          # recording, title search, etc.
        "quiet_title_cost": 2500,       # many tax deeds need quiet title to be insurable
        "assessed_to_market_ratio": 1.0,  # if county assesses at e.g. 80% of market, use 0.8
        "max_bid_to_value": 0.6,        # land: skip deals where all-in cost > 60% of value
    },
    # --- houses to renovate ---
    "rehab": {
        # Renovation cost per sq ft of living area by scope. Set these to YOUR local contractor prices.
        #   light  = paint, flooring, fixtures, cleanup
        #   medium = + kitchen/baths, some systems
        #   heavy  = + roof, HVAC, electrical/plumbing, structural repairs
        #   gut    = down to the studs (or teardown)
        "cost_per_sqft": {"light": 20, "medium": 40, "heavy": 70, "gut": 120},
        "fixed_costs": 5000,            # cleanout, locks, permits, utility turn-on
        "pre_1978_per_sqft": 5,         # lead paint precautions
        "pre_1950_per_sqft": 15,        # likely old wiring/plumbing
        "contingency_pct": 15,          # you can't inspect inside before a tax sale
        "unknown_condition_tier": "medium",
        "max_tier": "medium",           # FAIL anything needing more than this
        "max_rehab_cost": 60000,
        "eviction_cost": 3500,          # if occupied
        "arv_factor": 0.70,             # 70% rule: max all-in = 70% of ARV - repairs
        "holding_months": 6,
        "holding_cost_per_month": 800,  # taxes, insurance, utilities
        "selling_cost_pct": 8,          # agent + closing when you sell
        "min_profit": 20000,
        "allow_sfha": True,             # existing houses in flood zones: allowed but flagged
        # Map your county's condition grades to tiers (lowercase). Added to the built-ins below.
        "condition_map": {},
    },
    "red_flag_keywords": [
        "common area", "common element", "drainage", "retention", "detention",
        "easement", "ingress", "egress", "strip", "sliver", "right of way",
        "r/w", "hoa", "cemetery", "pond", "canal", "landlocked", "undivided",
        "mineral", "subsurface", "submerged", "condemned", "demolition order",
        "unsafe structure", "fire damage", "mobile home",
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
