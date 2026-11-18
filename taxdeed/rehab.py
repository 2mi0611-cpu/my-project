"""Renovation cost and flip/rental math for houses.

Tax deed houses are usually sold as-is with no interior inspection, so this
works from what the assessor knows (size, age, condition grade) plus a
contingency. Treat the result as a screening estimate; drive by, and check
permits and code violations before bidding.
"""
from __future__ import annotations

from .models import Parcel

TIERS = ["light", "medium", "heavy", "gut"]

# Common assessor condition grades -> renovation scope
CONDITION_TIERS = {
    "excellent": "light", "very good": "light", "good": "light", "average": "light",
    "normal": "light", "fair": "medium", "below average": "medium", "worn": "medium",
    "poor": "heavy", "badly worn": "heavy", "very poor": "gut", "unsound": "gut",
    "dilapidated": "gut", "condemned": "gut", "uninhabitable": "gut",
}


def condition_tier(condition: str, extra_map: dict | None = None) -> str | None:
    c = (condition or "").strip().lower()
    if not c:
        return None
    mapping = {**CONDITION_TIERS, **{k.lower(): v for k, v in (extra_map or {}).items()}}
    if c in mapping:
        return mapping[c]
    # Fall back to the longest grade name contained in the text ("POOR - ROOF DAMAGE").
    for name in sorted(mapping, key=len, reverse=True):
        if name in c:
            return mapping[name]
    return None


def estimate(p: Parcel, cfg: dict) -> None:
    """Fill rehab tier/cost, max bid, profit, ROI and rent yield on the parcel."""
    r, val = cfg["rehab"], cfg["value"]
    notes = p.notes

    tier = condition_tier(p.condition, r.get("condition_map"))
    if tier is None:
        tier = r["unknown_condition_tier"]
        notes.append(f"condition unknown - assumed {tier} rehab")
    if p.code_violations and p.code_violations >= 3 and tier in ("light", "medium"):
        tier = TIERS[TIERS.index(tier) + 1]
        notes.append(f"{int(p.code_violations)} code violations - bumped scope to {tier}")
    p.rehab_tier = tier

    if p.building_sqft:
        per_sqft = r["cost_per_sqft"][tier]
        if p.year_built and p.year_built < 1950:
            per_sqft += r["pre_1950_per_sqft"]
            notes.append("built before 1950 - budgeted for old wiring/plumbing")
        elif p.year_built and p.year_built < 1978:
            per_sqft += r["pre_1978_per_sqft"]
            notes.append("built before 1978 - lead paint likely")
        cost = (r["fixed_costs"] + p.building_sqft * per_sqft) * (1 + r["contingency_pct"] / 100)
        if p.occupied:
            cost += r["eviction_cost"]
        p.est_rehab_cost = round(cost, -2)
    else:
        p.est_rehab_cost = None

    if p.est_arv is None and p.est_market_value:
        # Weak fallback: assessed value is as-is, not after-repair. Get real comps.
        p.est_arv = p.est_market_value
        notes.append("ARV taken from assessed value - pull sold comps")

    p.max_bid = p.ideal_bid = p.est_profit = p.roi = p.rent_yield = None
    if p.est_arv and p.est_rehab_cost is not None:
        fixed = val["closing_costs"] + val["quiet_title_cost"]
        holding = r["holding_months"] * r["holding_cost_per_month"]
        selling = p.est_arv * r["selling_cost_pct"] / 100
        arv, repairs = p.est_arv, p.est_rehab_cost

        def bid_for_profit(target: float) -> float:
            """The opening-bid price at which the flip nets exactly `target`."""
            return arv - selling - repairs - holding - fixed - target

        # Max bid: the stricter of the 70% rule and the minimum-profit price.
        rule_70 = arv * r["arv_factor"] - repairs - fixed
        p.max_bid = round(min(rule_70, bid_for_profit(r["min_profit"])), -2)
        p.ideal_bid = round(min(p.max_bid, bid_for_profit(r["target_profit"])), -2)
        if p.opening_bid is not None and p.ideal_bid < p.opening_bid <= p.max_bid:
            notes.append("opening bid is above your ideal bid - margin will be thinner than target")
        if p.opening_bid is not None:
            acquisition = p.opening_bid + fixed
            cash_in = acquisition + p.est_rehab_cost + holding
            p.est_profit = round(p.est_arv - cash_in - selling, -2)
            p.roi = round(p.est_profit / cash_in, 3) if cash_in else None
            if p.est_rent:
                p.rent_yield = round(p.est_rent * 12 / (acquisition + p.est_rehab_cost), 3)
