from __future__ import annotations

import csv
import html

from .models import Parcel

COLUMNS = [
    "deal_score", "buildable_status", "county", "parcel_id", "address", "sale_date",
    "opening_bid", "est_market_value", "est_equity", "bid_to_value", "lot_acres",
    "zoning", "flood_zone", "wetlands", "slope_pct", "road_frontage",
    "buildable_reasons", "red_flags", "lat", "lon",
]


def _ranked(parcels: list[Parcel]) -> list[Parcel]:
    return sorted(parcels, key=lambda p: (p.deal_score or 0), reverse=True)


def _cell(p: Parcel, col: str):
    v = getattr(p, col)
    if isinstance(v, list):
        return "; ".join(v)
    return "" if v is None else v


def write_csv(parcels: list[Parcel], path: str) -> None:
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(COLUMNS)
        for p in _ranked(parcels):
            w.writerow([_cell(p, c) for c in COLUMNS])


def write_html(parcels: list[Parcel], path: str) -> None:
    rows = []
    for p in _ranked(parcels):
        cells = []
        for c in COLUMNS:
            v = _cell(p, c)
            if c in {"opening_bid", "est_market_value", "est_equity"} and v != "":
                v = f"${v:,.0f}"
            cls = f' class="{p.buildable_status.lower()}"' if c == "buildable_status" else ""
            cells.append(f"<td{cls}>{html.escape(str(v))}</td>")
        if p.lat is not None and p.lon is not None:
            cells.append(f'<td><a href="https://www.google.com/maps?q={p.lat},{p.lon}" '
                         f'target="_blank" rel="noopener">map</a></td>')
        else:
            cells.append("<td></td>")
        rows.append("<tr>" + "".join(cells) + "</tr>")
    head = "".join(f"<th>{c.replace('_', ' ')}</th>" for c in COLUMNS) + "<th></th>"
    doc = f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Tax Deed Deals</title>
<style>
body{{font:13px system-ui,sans-serif;margin:16px;background:#fff;color:#111}}
.wrap{{overflow-x:auto}} table{{border-collapse:collapse}}
th,td{{border:1px solid #ddd;padding:4px 6px;vertical-align:top;white-space:nowrap}}
td:nth-child(17),td:nth-child(18){{white-space:normal;min-width:220px}}
th{{background:#f4f4f4;position:sticky;top:0}}
.pass{{background:#d9f2dc}} .fail{{background:#f8d7d7}} .review{{background:#fff3c4}}
</style></head><body>
<h1>Tax Deed Deals</h1>
<p>{len(parcels)} parcels, ranked by deal score. PASS = all buildability checks passed,
REVIEW = data missing, FAIL = a hard check failed. Screening only &mdash; verify every
parcel (title, zoning, survey, site visit) before bidding.</p>
<div class="wrap"><table><thead><tr>{head}</tr></thead><tbody>
{''.join(rows)}
</tbody></table></div></body></html>"""
    with open(path, "w") as f:
        f.write(doc)
