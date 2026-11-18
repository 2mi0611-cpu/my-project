from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class Parcel:
    """One property from an auction or distressed-property list, plus everything we learn about it."""

    # --- from the list ---
    parcel_id: str
    county: str = ""
    state: str = ""
    address: str = ""
    legal_description: str = ""
    owner_name: str = ""
    sale_date: str = ""
    opening_bid: Optional[float] = None      # opening bid, or asking price for non-auction lists
    assessed_value: Optional[float] = None
    lot_acres: Optional[float] = None
    lot_width_ft: Optional[float] = None
    zoning: str = ""
    land_use: str = ""
    improved: Optional[bool] = None          # True if a structure is on it
    road_frontage: Optional[bool] = None     # True if it touches a public road
    lat: Optional[float] = None
    lon: Optional[float] = None

    # --- building details (houses) ---
    building_sqft: Optional[float] = None
    year_built: Optional[float] = None
    bedrooms: Optional[float] = None
    bathrooms: Optional[float] = None
    condition: str = ""                      # assessor condition grade, e.g. Good / Fair / Poor
    occupied: Optional[bool] = None
    code_violations: Optional[float] = None
    est_arv: Optional[float] = None          # after-repair value, from sold comps
    est_rent: Optional[float] = None         # monthly market rent

    # --- enrichment (filled in by taxdeed.enrich) ---
    flood_zone: Optional[str] = None
    in_sfha: Optional[bool] = None           # FEMA Special Flood Hazard Area
    wetlands: Optional[bool] = None
    wetland_types: str = ""
    elevation_ft: Optional[float] = None
    slope_pct: Optional[float] = None
    est_market_value: Optional[float] = None  # as-is value (land value for lots)

    # --- scoring (filled in by taxdeed.scoring) ---
    strategy: str = ""                       # "land" (build) or "rehab" (renovate)
    status: str = ""                         # PASS / FAIL / REVIEW
    reasons: list[str] = field(default_factory=list)
    red_flags: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    est_equity: Optional[float] = None
    bid_to_value: Optional[float] = None
    rehab_tier: str = ""                     # light / medium / heavy / gut
    est_rehab_cost: Optional[float] = None
    max_bid: Optional[float] = None          # walk-away price (never bid above)
    ideal_bid: Optional[float] = None        # bid that leaves your target profit
    est_profit: Optional[float] = None
    roi: Optional[float] = None
    rent_yield: Optional[float] = None
    deal_score: Optional[float] = None
    is_new: bool = False                     # first time seen by the automatic run
    source: str = ""                         # which source in sources.yaml it came from

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Parcel":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in known})
