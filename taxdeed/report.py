from __future__ import annotations

import csv
import html

from .models import Parcel


def usd(v: float) -> str:
    return f"-${abs(v):,.0f}" if v < 0 else f"${v:,.0f}"


COMMON = ["deal_score", "status", "is_new", "strategy", "county", "parcel_id", "address",
          "sale_date", "opening_bid", "ideal_bid", "max_bid"]
LAND = ["est_market_value", "est_equity", "bid_to_value", "lot_acres", "zoning",
        "flood_zone", "wetlands", "slope_pct", "road_frontage"]
REHAB = ["est_arv", "est_rehab_cost", "rehab_tier", "est_profit", "roi",
         "rent_yield", "building_sqft", "year_built", "bedrooms", "bathrooms", "condition",
         "occupied", "flood_zone"]
TAIL = ["reasons", "red_flags", "notes", "lat", "lon"]
MONEY = {"opening_bid", "est_market_value", "est_equity", "max_bid", "ideal_bid", "est_arv",
         "est_rehab_cost", "est_profit"}
PCT = {"roi", "rent_yield"}
WIDE = {"reasons", "red_flags", "notes"}


def columns(strategy: str | None) -> list[str]:
    if strategy == "land":
        middle = LAND
    elif strategy == "rehab":
        middle = REHAB
    else:
        middle = LAND + [c for c in REHAB if c not in LAND]
    return COMMON + middle + TAIL


def _ranked(parcels: list[Parcel]) -> list[Parcel]:
    return sorted(parcels, key=lambda p: (p.deal_score or 0), reverse=True)


def _cell(p: Parcel, col: str):
    v = getattr(p, col)
    if isinstance(v, list):
        return "; ".join(v)
    return "" if v is None else v


def _fmt(col: str, v):
    if col == "is_new":
        return "NEW" if v else ""
    if v == "":
        return v
    if col in MONEY:
        return usd(v)
    if col in PCT:
        return f"{v:.0%}"
    return v


def write_csv(parcels: list[Parcel], path: str, strategy: str | None = None) -> None:
    cols = columns(strategy)
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for p in _ranked(parcels):
            w.writerow([_cell(p, c) for c in cols])


def write_html(parcels: list[Parcel], path: str, strategy: str | None = None) -> None:
    cols = columns(strategy)
    rows = []
    for p in _ranked(parcels):
        cells = []
        for c in cols:
            v = _fmt(c, _cell(p, c))
            classes = []
            if c == "status":
                classes.append(p.status.lower())
            if c in WIDE:
                classes.append("wide")
            cls = f' class="{" ".join(classes)}"' if classes else ""
            cells.append(f"<td{cls}>{html.escape(str(v))}</td>")
        if p.lat is not None and p.lon is not None:
            cells.append(f'<td><a href="https://www.google.com/maps?q={p.lat},{p.lon}" '
                         f'target="_blank" rel="noopener">map</a></td>')
        else:
            cells.append("<td></td>")
        rows.append("<tr>" + "".join(cells) + "</tr>")
    head = "".join(f"<th>{c.replace('_', ' ')}</th>" for c in cols) + "<th></th>"
    title = {"land": "Buildable Land", "rehab": "Rehab Deals"}.get(strategy or "", "Tax Deed Deals")
    doc = f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>
body{{font:13px system-ui,sans-serif;margin:16px;background:#fff;color:#111}}
.wrap{{overflow-x:auto}} table{{border-collapse:collapse}}
th,td{{border:1px solid #ddd;padding:4px 6px;vertical-align:top;white-space:nowrap}}
td.wide{{white-space:normal;min-width:220px}}
th{{background:#f4f4f4;position:sticky;top:0}}
.pass{{background:#d9f2dc}} .fail{{background:#f8d7d7}} .review{{background:#fff3c4}}
</style></head><body>
<h1>{title}</h1>
<p>{len(parcels)} properties, ranked by deal score. <b>land</b> = vacant lot checked for
buildability; <b>rehab</b> = house checked for renovation cost and flip profit
<b>Ideal bid</b> = the bid that leaves your target profit; <b>max bid</b> = the most you
should ever bid (walk away above it).
PASS = all checks passed, REVIEW = data missing, FAIL = a hard check failed.
Screening only &mdash; verify title, zoning, condition and comps before bidding.</p>
<div class="wrap"><table><thead><tr>{head}</tr></thead><tbody>
{''.join(rows)}
</tbody></table></div></body></html>"""
    with open(path, "w") as f:
        f.write(doc)
