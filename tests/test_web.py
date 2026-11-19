import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from taxdeed import auto, overrides, web
from taxdeed.config import load_config
from taxdeed.db import Store
from taxdeed.models import Parcel
from taxdeed.scoring import score

CFG = load_config()


@pytest.fixture
def app(tmp_path):
    db = tmp_path / "t.db"
    store = Store(db)
    parcels = [
        # Putnam-style entry: price only, nothing to value it by
        Parcel(parcel_id="04-10-24-0001", county="Putnam", state="FL", opening_bid=1767.17,
               legal_description="LOT 25 <script>alert(1)</script>", owner_name="O'Brien & Sons"),
        # A complete vacant lot
        Parcel(parcel_id="L1", county="Sample", state="FL", address="1 Main St", opening_bid=4000,
               assessed_value=40000, lot_acres=0.5, lot_width_ft=100, road_frontage=True, improved=False),
    ]
    for p in parcels:
        score(p, CFG)
    store.upsert(parcels)
    store.close()
    ui = tmp_path / "overrides.ui.csv"
    srv = web.make_server(db, CFG, ui, "127.0.0.1", 0)
    threading.Thread(target=lambda: srv.serve_forever(poll_interval=0.01), daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    yield {"base": base, "db": db, "ui": ui, "tmp": tmp_path}
    srv.shutdown()
    srv.server_close()


def get(url):
    with urllib.request.urlopen(url) as r:
        return r.status, r.headers, r.read()


def post(base, body, headers=None):
    h = {"Content-Type": "application/json", "X-Taxdeed": "1"} if headers is None else headers
    req = urllib.request.Request(base + "/api/edit", data=json.dumps(body).encode(), headers=h, method="POST")
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_pages_are_served_with_security_headers(app):
    for path, marker in [("/", b"Tax Deed Deals"), ("/app.js", b"use strict"), ("/app.css", b"--bg")]:
        status, headers, body = get(app["base"] + path)
        assert status == 200 and marker in body
        assert "default-src 'self'" in headers["Content-Security-Policy"]
        assert headers["X-Content-Type-Options"] == "nosniff"


def test_api_lists_parcels_and_flags_missing_data(app):
    _, _, body = get(app["base"] + "/api/parcels")
    data = json.loads(body)
    by = {p["parcel_id"]: p for p in data["parcels"]}
    assert data["min_score"] == 40
    assert by["04-10-24-0001"]["needs_data"] is True
    assert by["L1"]["needs_data"] is False
    assert by["L1"]["ideal_bid"] == 12000 and by["L1"]["max_bid"] == 20000


def test_unknown_path_is_404(app):
    with pytest.raises(urllib.error.HTTPError) as e:
        get(app["base"] + "/etc/passwd")
    assert e.value.code == 404


def test_editing_rescores_and_persists(app):
    st, p = post(app["base"], {"county": "Putnam", "parcel_id": "04-10-24-0001",
                               "changes": {"assessed_value": 8000, "lot_acres": 0.25,
                                           "lot_width_ft": 80, "road_frontage": True, "improved": False}})
    assert st == 200
    assert p["needs_data"] is False
    # 60% of 8000 minus 4000 closing/quiet title = 800; the bid (1767) is above it
    assert p["max_bid"] == 800 and p["status"] == "FAIL"
    # saved to the database ...
    s = Store(app["db"])
    assert s.get("Putnam", "04-10-24-0001").assessed_value == 8000
    s.close()
    # ... and to the overrides file
    saved = overrides.load(app["ui"])
    assert saved[("Putnam", "04-10-24-0001")]["assessed_value"] == "8000"
    assert saved[("Putnam", "04-10-24-0001")]["road_frontage"] == "Y"


def test_changing_assessed_value_rebuilds_derived_value(app):
    base = app["base"]
    post(base, {"county": "Sample", "parcel_id": "L1", "changes": {"assessed_value": 100000}})
    st, p = post(base, {"county": "Sample", "parcel_id": "L1", "changes": {"assessed_value": 50000}})
    assert st == 200 and p["est_market_value"] == 50000     # not stuck at the first value


def test_clearing_a_value_removes_it_from_the_file(app):
    base = app["base"]
    post(base, {"county": "Sample", "parcel_id": "L1", "changes": {"zoning": "R-1", "est_rent": 900}})
    st, p = post(base, {"county": "Sample", "parcel_id": "L1", "changes": {"zoning": ""}})
    assert st == 200 and p["zoning"] == ""
    assert overrides.load(app["ui"])[("Sample", "L1")] == {"est_rent": "900"}


@pytest.mark.parametrize("changes", [
    {"assessed_value": "abc"}, {"assessed_value": -5}, {"assessed_value": float("inf")},
    {"year_built": 1200}, {"improved": "yes"}, {"zoning": "x" * 500},
    {"status": "PASS"}, {"deal_score": 100}, {"parcel_id": "hacked"}, {}, "nope",
])
def test_bad_edits_are_rejected_and_change_nothing(app, changes):
    st, body = post(app["base"], {"county": "Sample", "parcel_id": "L1", "changes": changes})
    assert st == 400 and "error" in body
    s = Store(app["db"])
    assert s.get("Sample", "L1").assessed_value == 40000
    s.close()
    assert not app["ui"].exists()


def test_unknown_property_is_404(app):
    st, _ = post(app["base"], {"county": "Nowhere", "parcel_id": "X", "changes": {"est_rent": 1}})
    assert st == 404


def test_cross_site_style_posts_are_refused(app):
    body = {"county": "Sample", "parcel_id": "L1", "changes": {"est_rent": 1}}
    assert post(app["base"], body, headers={"Content-Type": "application/json"})[0] == 403   # no custom header
    assert post(app["base"], body, headers={"Content-Type": "text/plain", "X-Taxdeed": "1"})[0] == 403
    assert not app["ui"].exists()


def test_values_entered_in_the_interface_survive_a_fresh_scan(app, tmp_path):
    post(app["base"], {"county": "Sample", "parcel_id": "L1", "changes": {"assessed_value": 90000}})
    src = tmp_path / "sources.yaml"
    csv = tmp_path / "list.csv"
    csv.write_text("Parcel Number,Minimum Bid,Assessed,Acres,Lot Width,Road Frontage,Improved,Address\n"
                   "L1,4000,40000,0.5,100,Y,N,1 Main St\n")
    src.write_text(f"sources:\n  - {{name: s, county: Sample, state: FL, file: {csv}}}\n")
    store = Store(app["db"])
    res = auto.run(CFG, store, sources_path=str(src), overrides_path=None,
                   ui_overrides_path=str(app["ui"]), out_root=str(tmp_path / "r"),
                   raw_dir=str(tmp_path / "raw"), skip_enrich=True)
    store.close()
    p = next(p for p in res["shortlist"] if p.parcel_id == "L1")
    assert p.assessed_value == 90000        # your number beat the freshly downloaded 40000


def test_page_has_no_inline_styles_or_scripts():
    # The server's security policy blocks inline styles and scripts, so the page must not use any.
    static = Path(web.__file__).parent / "static"
    js, html = (static / "app.js").read_text(), (static / "index.html").read_text()
    assert "style:" not in js and "setAttribute('style'" not in js
    assert "style=" not in html and "<script>" not in html and "onclick=" not in html
