import datetime as dt
from pathlib import Path

import pytest
import yaml

from taxdeed import auto, fetch
from taxdeed.config import load_config
from taxdeed.db import Store
from taxdeed.enrich import elevation, flood, wetlands
from taxdeed.models import Parcel
from taxdeed.scoring import score

SAMPLE = str(Path(__file__).parent.parent / "sample_data" / "sample_auction.csv")
DAY = dt.date(2026, 12, 1)


def _fake_services(monkeypatch):
    monkeypatch.setattr("taxdeed.enrich.geocode.geocode", lambda a: (27.9, -81.8))
    monkeypatch.setattr(flood, "flood_zone", lambda la, lo: ("X", False))
    monkeypatch.setattr(wetlands, "wetlands", lambda la, lo: (False, ""))
    monkeypatch.setattr(elevation, "slope_pct", lambda la, lo, a: (120.0, 3.0))


def _sources(tmp_path, *extra):
    p = tmp_path / "sources.yaml"
    p.write_text(yaml.safe_dump({"sources": [
        {"name": "sample", "county": "Sample", "state": "FL", "file": SAMPLE}, *extra]}))
    return str(p)


def _run(tmp_path, store, **kw):
    sources = kw.pop("sources", None) or _sources(tmp_path)
    return auto.run(load_config(), store, sources_path=sources,
                    overrides_path=kw.pop("overrides", None), out_root=str(tmp_path / "reports"),
                    raw_dir=str(tmp_path / "raw"), today=DAY, **kw)


# ---------------------------------------------------------------- bid math

def test_rehab_ideal_bid_hits_target_profit():
    p = Parcel(parcel_id="H", address="1 St", improved=True, opening_bid=15000,
               assessed_value=60000, building_sqft=1200, year_built=1995,
               condition="Average", est_arv=175000)
    score(p, load_config())
    assert p.max_bid == 85100          # 70% rule is the stricter of the two caps here
    assert p.ideal_bid == 78800
    # Bidding exactly the ideal bid should net the $40k target.
    q = Parcel(**{**p.to_dict(), "opening_bid": 78800})
    score(q, load_config())
    assert q.est_profit == 40000


def test_load_config_does_not_leak_edits():
    cfg = load_config()
    cfg["rehab"]["min_profit"] = 1
    assert load_config()["rehab"]["min_profit"] == 20000


def test_max_bid_uses_min_profit_when_stricter_than_70_rule():
    cfg = load_config()
    cfg["rehab"]["min_profit"] = 60000
    p = Parcel(parcel_id="H", improved=True, opening_bid=1000, building_sqft=1200,
               year_built=1995, condition="Average", est_arv=175000, address="x")
    score(p, cfg)
    # 175000 - 14000 selling - 33400 - 4800 - 4000 - 60000 = 58,800  (< 70% rule 85,100)
    assert p.max_bid == 58800
    assert p.ideal_bid == 58800        # ideal can never exceed max


def test_land_ideal_and_max_bid():
    p = Parcel(parcel_id="L", address="x", opening_bid=4000, assessed_value=40000,
               lot_acres=0.5, lot_width_ft=100, road_frontage=True, improved=False)
    score(p, load_config())
    assert p.max_bid == 20000          # 60% of 40k - 4k
    assert p.ideal_bid == 12000        # 40% of 40k - 4k


def test_opening_bid_above_max_bid_fails_land():
    p = Parcel(parcel_id="L", address="x", opening_bid=9800, assessed_value=22000,
               lot_acres=1.2, lot_width_ft=150, road_frontage=True, improved=False)
    score(p, load_config())
    assert p.status == "FAIL"
    assert any("above max bid" in r for r in p.reasons)


def test_opening_bid_between_ideal_and_max_is_noted():
    p = Parcel(parcel_id="L", address="x", opening_bid=15000, assessed_value=40000,
               lot_acres=0.5, lot_width_ft=100, road_frontage=True, improved=False)
    score(p, load_config())
    assert any("above your ideal bid" in n for n in p.notes)


# ---------------------------------------------------------------- the run

def test_auto_run_builds_shortlist(monkeypatch, tmp_path):
    _fake_services(monkeypatch)
    store = Store(tmp_path / "t.db")
    res = _run(tmp_path, store)
    assert res["total"] == 6 and res["new"] == 6 and not res["errors"]
    top = res["shortlist"][0]
    assert top.parcel_id == "SAMPLE-004"
    assert top.ideal_bid <= top.max_bid
    out = Path(res["out_dir"])
    assert out.name == "2026-12-01"
    for f in ("shortlist.html", "shortlist.csv", "all.html", "all.csv"):
        assert (out / f).exists()
    csv_text = (out / "shortlist.csv").read_text()
    assert "ideal_bid" in csv_text and "max_bid" in csv_text
    assert "SAMPLE-002" not in csv_text        # the drainage strip must not be shortlisted
    store.close()


def test_second_run_marks_nothing_new_and_skips_lookups(monkeypatch, tmp_path):
    _fake_services(monkeypatch)
    store = Store(tmp_path / "t.db")
    _run(tmp_path, store)
    monkeypatch.setattr(flood, "flood_zone",
                        lambda la, lo: pytest.fail("already-looked-up parcel was fetched again"))
    res = _run(tmp_path, store)
    assert res["new"] == 0
    store.close()


def test_overrides_replace_arv(monkeypatch, tmp_path):
    _fake_services(monkeypatch)
    ov = tmp_path / "overrides.csv"
    ov.write_text("Parcel Number,ARV,Condition\nSAMPLE-004,300000,Good\n")
    store = Store(tmp_path / "t.db")
    res = _run(tmp_path, store, overrides=str(ov))
    p = next(p for p in res["shortlist"] if p.parcel_id == "SAMPLE-004")
    assert p.est_arv == 300000
    store.close()


def test_failed_properties_are_not_looked_up(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr("taxdeed.enrich.geocode.geocode", lambda a: (seen.append(a), (27.9, -81.8))[1])
    monkeypatch.setattr(flood, "flood_zone", lambda la, lo: ("X", False))
    monkeypatch.setattr(wetlands, "wetlands", lambda la, lo: (False, ""))
    monkeypatch.setattr(elevation, "slope_pct", lambda la, lo, a: (120.0, 3.0))
    store = Store(tmp_path / "t.db")
    _run(tmp_path, store)
    # SAMPLE-002 (sliver, no address) and SAMPLE-006 (heavy rehab) fail on list data alone.
    assert not any("Mock St" in a for a in seen)
    store.close()


def test_one_bad_source_does_not_stop_the_others(monkeypatch, tmp_path):
    _fake_services(monkeypatch)
    src = _sources(tmp_path, {"name": "broken", "file": str(tmp_path / "missing.csv")})
    store = Store(tmp_path / "t.db")
    res = _run(tmp_path, store, sources=src)
    assert "broken" in res["errors"]
    assert res["total"] == 6 and res["sources_ok"] == 1
    store.close()


def test_cli_auto_returns_nonzero_on_source_error(monkeypatch, tmp_path, capsys):
    from taxdeed import cli
    _fake_services(monkeypatch)
    src = _sources(tmp_path, {"name": "broken", "file": str(tmp_path / "missing.csv")})
    rc = cli.main(["--db", str(tmp_path / "t.db"), "auto", "--sources", src,
                   "--overrides", str(tmp_path / "none.csv"), "--out-dir", str(tmp_path / "r"),
                   "--raw-dir", str(tmp_path / "raw")])
    out = capsys.readouterr()
    assert rc == 1
    assert "ideal bid" in out.out and "broken" in out.err


# ---------------------------------------------------------------- fetching

class _Resp:
    def __init__(self, content: bytes):
        self.content = content

    def raise_for_status(self):
        pass


def test_download_url_source(monkeypatch, tmp_path):
    monkeypatch.setattr(fetch.requests, "get",
                        lambda url, **k: _Resp(Path(SAMPLE).read_bytes()))
    path = fetch.fetch_source({"name": "web", "url": "https://example.gov/list.csv"},
                              tmp_path / "raw", DAY)
    assert path.read_text().startswith("Parcel Number")


def test_html_instead_of_spreadsheet_is_rejected(monkeypatch, tmp_path):
    monkeypatch.setattr(fetch.requests, "get",
                        lambda url, **k: _Resp(b"<!DOCTYPE html><html>Please log in</html>"))
    with pytest.raises(RuntimeError, match="web page"):
        fetch.fetch_source({"name": "web", "url": "https://example.gov/list"},
                           tmp_path / "raw", DAY)


def test_skip_rows_removes_title_lines(tmp_path):
    f = tmp_path / "list.csv"
    f.write_text("COUNTY TAX DEED SALE\nprinted 12/1\n" + Path(SAMPLE).read_text())
    path = fetch.fetch_source({"name": "t", "file": str(f), "skip_rows": 2}, tmp_path / "raw", DAY)
    assert path.read_text().startswith("Parcel Number")


def test_xlsx_source(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Parcel Number", "Minimum Bid", "Assessed", "Sqft", "Condition", "Improved"])
    ws.append(["X-1", 5000, 50000, 1000, "Good", "Y"])
    f = tmp_path / "list.xlsx"
    wb.save(f)
    from taxdeed.importers.csv_import import import_csv
    path = fetch.fetch_source({"name": "x", "file": str(f)}, tmp_path / "raw", DAY)
    p = import_csv(str(path), county="C")[0]
    assert (p.parcel_id, p.opening_bid, p.building_sqft, p.improved) == ("X-1", 5000, 1000, True)


def test_sources_validation(tmp_path):
    f = tmp_path / "s.yaml"
    f.write_text("sources:\n  - name: a\n")
    with pytest.raises(ValueError, match="url or a file"):
        fetch.load_sources(str(f))
    f.write_text("sources:\n  - {name: a, file: x}\n  - {name: a, file: y}\n")
    with pytest.raises(ValueError, match="duplicate"):
        fetch.load_sources(str(f))


def test_report_columns_cannot_be_imported_back(tmp_path):
    from taxdeed.importers.csv_import import import_csv
    f = tmp_path / "re.csv"
    f.write_text("parcel_id,status,notes,max_bid,deal_score\nP1,PASS,hello,5,99\n")
    p = import_csv(str(f))[0]
    assert p.status == "" and p.notes == [] and p.max_bid is None and p.deal_score is None


# ---------------------------------------------------------------- Putnam lands-available parser

PUTNAM = Path(__file__).parent / "fixtures" / "putnam_laft_sample.html"


def test_putnam_parser_reads_entries_and_skips_unreadable_blocks():
    from taxdeed.importers import putnam
    rows = putnam.parse_laft(PUTNAM.read_text())
    assert [r["parcel_id"] for r in rows] == ["04-10-24-9030-0050-0250", "13-10-26-0000-0650-0001"]
    a, b = rows
    assert a["owner_name"] == "EXAMPLE OWNER ONE LLC"
    assert a["legal_description"] == "TROUT LAKE GARDENS MB4 P68, BLK 5 LOT 25"
    assert (a["sale_date"], a["available_date"], a["opening_bid"]) == ("09/24/2025", "12/23/2025", "1767.17")
    assert a["case_number"] == "T.D. 2018-0003254"
    assert b["owner_name"] == "EXAMPLE OWNER TWO & SONS"
    assert b["available_date"] == "" and b["opening_bid"] == "20619.76"


def test_putnam_parser_rejects_wrong_page():
    from taxdeed.importers import putnam
    with pytest.raises(RuntimeError, match="Lands Available"):
        putnam.parse_laft("<html>Please accept our disclaimer</html>")


def test_putnam_source_flows_through_the_pipeline(monkeypatch, tmp_path):
    _fake_services(monkeypatch)
    monkeypatch.setattr(fetch.requests, "get", lambda url, **k: _Resp(PUTNAM.read_bytes()))
    src = tmp_path / "sources.yaml"
    src.write_text(yaml.safe_dump({"sources": [{
        "name": "putnam-lands", "county": "Putnam", "state": "FL", "parser": "putnam_laft",
        "url": "https://apps.putnam-fl.com/coc/taxdeeds/public/public_LAFT.php"}]}))
    store = Store(tmp_path / "t.db")
    res = _run(tmp_path, store, sources=str(src))
    assert res["total"] == 2 and not res["errors"]
    assert res["unvalued"] == 2                      # the list has no assessed value to rank by
    got = {p.parcel_id: p for p in store.all()}
    p = got["04-10-24-9030-0050-0250"]
    assert (p.opening_bid, p.available_date, p.county) == (1767.17, "12/23/2025", "Putnam")
    store.close()


def test_unknown_parser_is_an_error(tmp_path):
    with pytest.raises(ValueError, match="unknown parser"):
        fetch.fetch_source({"name": "x", "file": SAMPLE, "parser": "nope"}, tmp_path / "raw", DAY)
