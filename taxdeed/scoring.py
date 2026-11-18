"""Buildability check + deal score.

buildable_status:
  PASS   - every check passed with known data
  FAIL   - at least one hard check failed
  REVIEW - nothing failed, but some data was missing; check it by hand
"""
from __future__ import annotations

from .models import Parcel


def check_buildable(p: Parcel, rules: dict) -> tuple[str, list[str]]:
    fails, unknown = [], []

    def check(value, ok, fail_msg, unknown_msg):
        if value is None:
            unknown.append(unknown_msg)
        elif not ok(value):
            fails.append(fail_msg)

    check(p.lot_acres, lambda v: v >= rules["min_lot_acres"],
          f"lot {p.lot_acres} ac < min {rules['min_lot_acres']} ac", "lot size unknown")
    if rules.get("min_lot_width_ft"):
        check(p.lot_width_ft, lambda v: v >= rules["min_lot_width_ft"],
              f"lot width {p.lot_width_ft} ft < min {rules['min_lot_width_ft']} ft", "lot width unknown")
    if not rules["allow_sfha"]:
        check(p.in_sfha, lambda v: not v,
              f"in FEMA high-risk flood zone {p.flood_zone}", "flood zone unknown")
    if not rules["allow_wetlands"]:
        check(p.wetlands, lambda v: not v,
              f"mapped wetlands ({p.wetland_types})", "wetlands unknown")
    check(p.slope_pct, lambda v: v <= rules["max_slope_pct"],
          f"slope ~{p.slope_pct}% > max {rules['max_slope_pct']}%", "slope unknown")
    if rules["require_road_frontage"]:
        check(p.road_frontage, bool, "no public road frontage (landlocked?)", "road frontage unknown")
    if rules["require_vacant"]:
        check(p.improved, lambda v: not v, "already improved (has a structure)", "vacant/improved unknown")
    allowed = [z.upper() for z in rules.get("allowed_zoning") or []]
    if allowed:
        check(p.zoning or None, lambda v: v.upper() in allowed,
              f"zoning {p.zoning} not in allowed list", "zoning unknown")

    if fails:
        return "FAIL", fails + unknown
    if unknown:
        return "REVIEW", unknown
    return "PASS", []


def red_flags(p: Parcel, keywords: list[str]) -> list[str]:
    text = f"{p.legal_description} {p.land_use} {p.address}".lower()
    flags = [f"keyword: '{k}'" for k in keywords if k in text]
    if p.lot_acres is not None and p.lot_acres < 0.05:
        flags.append("tiny parcel (< 0.05 ac)")
    if p.lot_width_ft is not None and p.lot_width_ft < 25:
        flags.append("very narrow (< 25 ft) - possible strip/sliver")
    if not p.address:
        flags.append("no street address")
    return flags


def score(p: Parcel, cfg: dict) -> Parcel:
    rules, val = cfg["buildable"], cfg["value"]
    p.buildable_status, p.buildable_reasons = check_buildable(p, rules)
    p.red_flags = red_flags(p, cfg["red_flag_keywords"])

    p.est_equity = p.bid_to_value = None
    if p.est_market_value is None and p.assessed_value:
        p.est_market_value = round(p.assessed_value / val["assessed_to_market_ratio"], 2)
    if p.est_market_value and p.opening_bid is not None:
        all_in = p.opening_bid + val["closing_costs"] + val["quiet_title_cost"]
        p.est_equity = round(p.est_market_value - all_in, 2)
        p.bid_to_value = round(all_in / p.est_market_value, 3)

    # 0-100. Value drives the score; buildability and flags gate/penalize it.
    s = 0.0
    if p.bid_to_value is not None:
        s = max(0.0, min(1.0, 1 - p.bid_to_value)) * 70        # cheaper vs value = better
        s += min(30.0, max(0.0, (p.est_equity or 0) / 1000))   # +1 per $1k equity, cap 30
        if p.bid_to_value > val["max_bid_to_value"]:
            s *= 0.5
    if p.buildable_status == "FAIL":
        s *= 0.2
    elif p.buildable_status == "REVIEW":
        s *= 0.8
    s -= 5 * len(p.red_flags)
    p.deal_score = round(max(0.0, s), 1)
    return p
