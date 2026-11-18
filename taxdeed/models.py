from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class Parcel:
    """One parcel offered at a tax deed sale, plus everything we learn about it."""

    # --- from the auction list ---
    parcel_id: str
    county: str = ""
    state: str = ""
    address: str = ""
    legal_description: str = ""
    sale_date: str = ""
    opening_bid: Optional[float] = None
    assessed_value: Optional[float] = None
    lot_acres: Optional[float] = None
    lot_width_ft: Optional[float] = None
    zoning: str = ""
    land_use: str = ""
    improved: Optional[bool] = None          # True if a structure is on it
    road_frontage: Optional[bool] = None     # True if it touches a public road
    lat: Optional[float] = None
    lon: Optional[float] = None

    # --- enrichment (filled in by taxdeed.enrich) ---
    flood_zone: Optional[str] = None
    in_sfha: Optional[bool] = None           # FEMA Special Flood Hazard Area
    wetlands: Optional[bool] = None
    wetland_types: str = ""
    elevation_ft: Optional[float] = None
    slope_pct: Optional[float] = None
    est_market_value: Optional[float] = None  # from comps or your own entry

    # --- scoring (filled in by taxdeed.scoring) ---
    buildable_status: str = ""               # PASS / FAIL / REVIEW
    buildable_reasons: list[str] = field(default_factory=list)
    red_flags: list[str] = field(default_factory=list)
    est_equity: Optional[float] = None
    bid_to_value: Optional[float] = None
    deal_score: Optional[float] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Parcel":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in known})
