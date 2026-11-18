from pathlib import Path

import pytest

from taxdeed import cli
from taxdeed.config import load_config
from taxdeed.db import Store
from taxdeed.enrich import elevation, flood, http, wetlands
from taxdeed.enrich.pipeline import enrich
from taxdeed.importers.csv_import import import_csv
from taxdeed.models import Parcel
from taxdeed.scoring import score

SAMPLE = Path(__file__).parent.parent / "sample_data" / "sample_auction.csv"


def test_import_maps_common_headers():
    parcels = import_csv(str(SAMPLE), county="Sample", state="FL")
    assert len(parcels) == 6
    p = parcels[0]
    assert p.parcel_id == "SAMPLE-001"
    assert p.opening_bid == 4200
    assert p.assessed_value == 38000
    assert p.lot_acres == 0.5
    assert p.lot_width_ft == 100
    assert p.improved is False and p.road_frontage is True
    assert p.county == "Sample" and p.state == "FL"


def test_flood_parses_fema_response(monkeypatch):
    monkeypatch.setattr(http, "get_json", lambda url, params, **k: {
        "features": [{"attributes": {"FLD_ZONE": "X", "SFHA_TF": "F"}},
                     {"attributes": {"FLD_ZONE": "AE", "SFHA_TF": "T"}}]})
    assert flood.flood_zone(27.0, -81.0) == ("AE", True)


def test_wetlands_parses_nwi_response(monkeypatch):
    monkeypatch.setattr(http, "get_json", lambda url, params, **k: {
        "features": [{"attributes": {"WETLAND_TYPE": "Freshwater Emergent Wetland"}}]})
    assert wetlands.wetlands(27.0, -81.0) == (True, "Freshwater Emergent Wetland")


def test_arcgis_error_raises(monkeypatch):
    monkeypatch.setattr(http, "get_json", lambda url, params, **k: {"error": {"code": 400}})
    with pytest.raises(RuntimeError):
        flood.flood_zone(27.0, -81.0)


def test_slope_from_elevation_samples():
    # Center 100 ft; one neighbor 10 ft higher.
    calls = iter([100, 110, 100, 100, 100])
    center, slope = elevation.slope_pct(27.0, -81.0, 1.0, elev_fn=lambda la, lo: next(calls))
    assert center == 100
    # 1 acre -> side ~63.6 m, run ~31.8 m ~ 104 ft -> ~9.6%
    assert 9 < slope < 10.5


def _fake_services(monkeypatch, zone="X", sfha=False, wet=False, slope=3.0):
    monkeypatch.setattr("taxdeed.enrich.geocode.geocode", lambda a: (27.9, -81.8))
    monkeypatch.setattr(flood, "flood_zone", lambda la, lo: (zone, sfha))
    monkeypatch.setattr(wetlands, "wetlands", lambda la, lo: (wet, "PEM1" if wet else ""))
    monkeypatch.setattr(elevation, "slope_pct", lambda la, lo, a: (120.0, slope))


def test_good_lot_passes_and_scores_high(monkeypatch):
    _fake_services(monkeypatch)
    cfg = load_config()
    p = Parcel(parcel_id="1", address="1 Main St", opening_bid=4000, assessed_value=40000,
               lot_acres=0.5, lot_width_ft=100, road_frontage=True, improved=False,
               legal_description="LOT 4 BLK 2")
    score(enrich(p), cfg)
    assert p.status == "PASS", p.reasons
    assert p.est_equity == 40000 - 4000 - 1500 - 2500
    assert p.deal_score > 60


def test_flood_zone_fails(monkeypatch):
    _fake_services(monkeypatch, zone="AE", sfha=True)
    p = Parcel(parcel_id="2", address="2 Main St", opening_bid=4000, assessed_value=40000,
               lot_acres=0.5, lot_width_ft=100, road_frontage=True)
    score(enrich(p), load_config())
    assert p.status == "FAIL"
    assert any("flood" in r for r in p.reasons)


def test_missing_data_is_review_not_pass(monkeypatch):
    monkeypatch.setattr(flood, "flood_zone", lambda la, lo: (_ for _ in ()).throw(RuntimeError("down")))
    monkeypatch.setattr(wetlands, "wetlands", lambda la, lo: (False, ""))
    monkeypatch.setattr(elevation, "slope_pct", lambda la, lo, a: (100.0, 2.0))
    p = Parcel(parcel_id="3", lat=27.0, lon=-81.0, opening_bid=1000, assessed_value=30000,
               lot_acres=0.5, lot_width_ft=80, road_frontage=True, address="3 Main St")
    score(enrich(p), load_config())
    assert p.status == "REVIEW"
    assert "flood zone unknown" in p.reasons


def test_sliver_lot_flagged(monkeypatch):
    _fake_services(monkeypatch)
    p = Parcel(parcel_id="4", opening_bid=350, assessed_value=1200, lot_acres=0.03,
               lot_width_ft=12, road_frontage=False, lat=27.0, lon=-81.0,
               legal_description="TRACT A COMMON AREA AND DRAINAGE")
    score(enrich(p), load_config())
    assert p.status == "FAIL"
    assert any("common area" in f for f in p.red_flags)
    assert any("narrow" in f for f in p.red_flags)
    assert p.deal_score < 10


def test_value_scored_without_enrichment():
    p = Parcel(parcel_id="5", opening_bid=4000, assessed_value=40000)
    score(p, load_config())
    assert p.est_market_value == 40000
    assert p.est_equity == 32000
    assert p.deal_score > 0


def test_cli_run_end_to_end(monkeypatch, tmp_path):
    _fake_services(monkeypatch)
    out = tmp_path / "deals.html"
    cli.main(["--db", str(tmp_path / "t.db"), "run", str(SAMPLE),
              "--county", "Sample", "--state", "FL", "--out", str(out)])
    html = out.read_text()
    assert "SAMPLE-001" in html and "SAMPLE-004" in html
    store = Store(tmp_path / "t.db")
    land = sorted((p for p in store.all() if p.strategy == "land"),
                  key=lambda p: p.deal_score, reverse=True)
    assert land[0].parcel_id == "SAMPLE-001"
    store.close()


# ------------------------------------------------------------- rehab strategy

from taxdeed import rehab  # noqa: E402


def test_condition_grades_map_to_tiers():
    assert rehab.condition_tier("Good") == "light"
    assert rehab.condition_tier("FAIR") == "medium"
    assert rehab.condition_tier("POOR - ROOF DAMAGE") == "heavy"
    assert rehab.condition_tier("Very Poor") == "gut"
    assert rehab.condition_tier("") is None
    assert rehab.condition_tier("C3", {"c3": "light"}) == "light"


def _house(**kw):
    base = dict(parcel_id="H1", address="1 House St", improved=True, opening_bid=15000,
                assessed_value=60000, building_sqft=1200, year_built=1995,
                condition="Average", occupied=False, est_arv=175000)
    base.update(kw)
    return Parcel(**base)


def test_light_rehab_math_and_pass():
    p = score(_house(), load_config())
    assert p.strategy == "rehab"
    assert p.rehab_tier == "light"
    # (5000 + 1200*20) * 1.15 = 33,350 -> 33,400
    assert p.est_rehab_cost == 33400
    # 175000*0.7 - 33400 - 1500 - 2500 = 85,100
    assert p.max_bid == 85100
    # cash in = 19000 + 33400 + 4800 = 57,200; selling 14,000; profit 103,800
    assert p.est_profit == 103800
    assert p.status == "PASS", p.reasons
    assert p.deal_score > 80


def test_heavy_rehab_fails_by_default():
    p = score(_house(condition="Poor"), load_config())
    assert p.rehab_tier == "heavy"
    assert p.status == "FAIL"
    assert any("heavy rehab" in r for r in p.reasons)


def test_old_occupied_house_costs_more_and_is_flagged():
    base = score(_house(), load_config()).est_rehab_cost
    p = score(_house(year_built=1940, occupied=True), load_config())
    assert p.est_rehab_cost > base + 3500
    assert any("occupied" in f for f in p.red_flags)
    assert any("1950" in n for n in p.notes)


def test_code_violations_bump_scope():
    p = score(_house(condition="Fair", code_violations=4), load_config())
    assert p.rehab_tier == "heavy"


def test_bid_above_max_bid_fails():
    p = score(_house(opening_bid=100000), load_config())
    assert p.status == "FAIL"
    assert any("above max bid" in r for r in p.reasons)


def test_unknown_condition_and_size_is_review():
    p = score(_house(condition="", building_sqft=None, est_arv=None), load_config())
    assert p.status == "REVIEW"
    assert any("building size unknown" in r for r in p.reasons)


def test_house_skips_wetland_and_slope_lookups(monkeypatch):
    monkeypatch.setattr(flood, "flood_zone", lambda la, lo: ("X", False))
    monkeypatch.setattr(wetlands, "wetlands", lambda *a: pytest.fail("should not call wetlands"))
    monkeypatch.setattr(elevation, "slope_pct", lambda *a: pytest.fail("should not call slope"))
    p = enrich(_house(lat=27.0, lon=-81.0))
    assert p.flood_zone == "X"


def test_report_strategy_filter(monkeypatch, tmp_path):
    _fake_services(monkeypatch)
    db = str(tmp_path / "t.db")
    cli.main(["--db", db, "run", str(SAMPLE), "--county", "Sample", "--state", "FL",
              "--out", str(tmp_path / "all.html")])
    out = tmp_path / "rehab.csv"
    cli.main(["--db", db, "report", "--strategy", "rehab", "--out", str(out)])
    lines = out.read_text().splitlines()
    assert len(lines) == 1 + 3                     # header + 3 houses
    assert "SAMPLE-004" in lines[1]                # light rehab ranks first
