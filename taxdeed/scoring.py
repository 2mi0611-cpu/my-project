"""Classify each parcel as a land deal or a rehab deal, check it, and score it.

status:
  PASS   - every check passed with known data
  FAIL   - at least one hard check failed
  REVIEW - nothing failed, but some data was missing; check it by hand
"""
from __future__ import annotations

from . import rehab
from .models import Parcel
from .report import usd


class _Checks:
    def __init__(self):
        self.fails: list[str] = []
        self.unknown: list[str] = []

    def check(self, value, ok, fail_msg, unknown_msg):
        if value is None:
            self.unknown.append(unknown_msg)
        elif not ok(value):
            self.fails.append(fail_msg)

    def result(self) -> tuple[str, list[str]]:
        if self.fails:
            return "FAIL", self.fails + self.unknown
        if self.unknown:
            return "REVIEW", self.unknown
        return "PASS", []


def strategy(p: Parcel) -> str:
    if p.improved is True or (p.improved is None and p.building_sqft):
        return "rehab"
    return "land"


# ---------------------------------------------------------------- land

def check_buildable(p: Parcel, rules: dict) -> tuple[str, list[str]]:
    c = _Checks()
    c.check(p.lot_acres, lambda v: v >= rules["min_lot_acres"],
            f"lot {p.lot_acres} ac < min {rules['min_lot_acres']} ac", "lot size unknown")
    if rules.get("min_lot_width_ft"):
        c.check(p.lot_width_ft, lambda v: v >= rules["min_lot_width_ft"],
                f"lot width {p.lot_width_ft} ft < min {rules['min_lot_width_ft']} ft", "lot width unknown")
    if not rules["allow_sfha"]:
        c.check(p.in_sfha, lambda v: not v,
                f"in FEMA high-risk flood zone {p.flood_zone}", "flood zone unknown")
    if not rules["allow_wetlands"]:
        c.check(p.wetlands, lambda v: not v,
                f"mapped wetlands ({p.wetland_types})", "wetlands unknown")
    c.check(p.slope_pct, lambda v: v <= rules["max_slope_pct"],
            f"slope ~{p.slope_pct}% > max {rules['max_slope_pct']}%", "slope unknown")
    if rules["require_road_frontage"]:
        c.check(p.road_frontage, bool, "no public road frontage (landlocked?)", "road frontage unknown")
    if rules["require_vacant"]:
        c.check(p.improved, lambda v: not v, "already improved (has a structure)", "vacant/improved unknown")
    allowed = [z.upper() for z in rules.get("allowed_zoning") or []]
    if allowed:
        c.check(p.zoning or None, lambda v: v.upper() in allowed,
                f"zoning {p.zoning} not in allowed list", "zoning unknown")
    return c.result()


def _score_land(p: Parcel, cfg: dict) -> float:
    val = cfg["value"]
    p.status, p.reasons = check_buildable(p, cfg["buildable"])
    p.max_bid = p.ideal_bid = None
    if p.est_market_value:
        fixed = val["closing_costs"] + val["quiet_title_cost"]
        p.max_bid = round(p.est_market_value * val["max_bid_to_value"] - fixed, -2)
        p.ideal_bid = round(min(p.max_bid, p.est_market_value * val["ideal_bid_to_value"] - fixed), -2)
        if p.opening_bid is not None and p.opening_bid > p.max_bid:
            p.status = "FAIL"
            p.reasons = [f"opening bid {usd(p.opening_bid)} already above max bid {usd(p.max_bid)}"] + p.reasons
        elif p.opening_bid is not None and p.opening_bid > p.ideal_bid:
            p.notes.append("opening bid is above your ideal bid - margin will be thinner than target")
    p.est_equity = p.bid_to_value = None
    if p.est_market_value and p.opening_bid is not None:
        all_in = p.opening_bid + val["closing_costs"] + val["quiet_title_cost"]
        p.est_equity = round(p.est_market_value - all_in, 2)
        p.bid_to_value = round(all_in / p.est_market_value, 3)

    s = 0.0
    if p.bid_to_value is not None:
        s = max(0.0, min(1.0, 1 - p.bid_to_value)) * 70        # cheaper vs value = better
        s += min(30.0, max(0.0, (p.est_equity or 0) / 1000))   # +1 per $1k equity, cap 30
        if p.bid_to_value > val["max_bid_to_value"]:
            s *= 0.5
    return s


# ---------------------------------------------------------------- rehab

def check_rehab(p: Parcel, r: dict) -> tuple[str, list[str]]:
    c = _Checks()
    max_i = rehab.TIERS.index(r["max_tier"])
    c.check(p.rehab_tier or None, lambda t: rehab.TIERS.index(t) <= max_i,
            f"needs {p.rehab_tier} rehab (max allowed: {r['max_tier']})", "rehab scope unknown")
    c.check(p.est_rehab_cost, lambda v: v <= r["max_rehab_cost"],
            f"est. rehab {usd(p.est_rehab_cost)} > max {usd(r['max_rehab_cost'])}"
            if p.est_rehab_cost else "", "building size unknown - can't estimate rehab")
    c.check(p.max_bid, lambda v: p.opening_bid is None or p.opening_bid <= v,
            f"opening bid {usd(p.opening_bid or 0)} already above max bid {usd(p.max_bid or 0)}",
            "ARV unknown - can't compute max bid")
    c.check(p.est_profit, lambda v: v >= r["min_profit"],
            f"est. profit {usd(p.est_profit or 0)} < min {usd(r['min_profit'])}", "profit unknown")
    if not r["allow_sfha"]:
        c.check(p.in_sfha, lambda v: not v, f"in FEMA high-risk flood zone {p.flood_zone}",
                "flood zone unknown")
    if any(n.startswith("condition unknown") for n in p.notes):
        c.unknown.append("condition unknown - drive by before bidding")
    return c.result()


def _score_rehab(p: Parcel, cfg: dict) -> float:
    r = cfg["rehab"]
    rehab.estimate(p, cfg)
    p.status, p.reasons = check_rehab(p, r)
    if p.occupied:
        p.red_flags.append("occupied - eviction needed")
    if p.code_violations:
        p.red_flags.append(f"{int(p.code_violations)} open code violation(s)")
    if p.in_sfha:
        p.red_flags.append(f"FEMA flood zone {p.flood_zone} - flood insurance required")

    s = 0.0
    if p.est_profit is not None and p.est_arv:
        margin = p.est_profit / p.est_arv
        s += max(0.0, min(1.0, margin / 0.30)) * 50           # 30%+ margin -> full 50
        s += max(0.0, min(1.0, (p.roi or 0) / 0.50)) * 30     # 50%+ ROI -> full 30
    s += {"light": 20, "medium": 10}.get(p.rehab_tier, 0)     # prefer low-renovation deals
    return s


# ---------------------------------------------------------------- shared

def red_flags(p: Parcel, keywords: list[str]) -> list[str]:
    text = f"{p.legal_description} {p.land_use} {p.address} {p.condition}".lower()
    flags = [f"keyword: '{k}'" for k in keywords if k in text]
    if p.lot_acres is not None and p.lot_acres < 0.05 and p.strategy == "land":
        flags.append("tiny parcel (< 0.05 ac)")
    if p.lot_width_ft is not None and p.lot_width_ft < 25:
        flags.append("very narrow (< 25 ft) - possible strip/sliver")
    if not p.address:
        flags.append("no street address")
    return flags


def score(p: Parcel, cfg: dict) -> Parcel:
    p.notes, p.red_flags = [], []
    p.strategy = strategy(p)
    if p.est_market_value is None and p.assessed_value:
        p.est_market_value = round(p.assessed_value / cfg["value"]["assessed_to_market_ratio"], 2)
    p.red_flags = red_flags(p, cfg["red_flag_keywords"])

    s = _score_rehab(p, cfg) if p.strategy == "rehab" else _score_land(p, cfg)
    if p.status == "FAIL":
        s *= 0.2
    elif p.status == "REVIEW":
        s *= 0.8
    s -= 5 * len(p.red_flags)
    p.deal_score = round(max(0.0, min(100.0, s)), 1)
    return p
