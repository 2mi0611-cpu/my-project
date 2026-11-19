"""Putnam County, FL: "Lands Available for Taxes" list (apps.putnam-fl.com/coc/taxdeeds/public/public_LAFT.php).

These are parcels that drew no bid at the tax deed auction. After the waiting period they can be
bought for the "estimated purchase price". The page is plain HTML: one block per parcel with the
certificate (T.D.) number, owner, legal description, parcel number, auction date, the date it
becomes available, and the price. It carries no address, lot size, zoning or assessed value, so
those must come from another source (see COUNTIES.md).
"""
from __future__ import annotations

import csv
import html
import re
from pathlib import Path

FIELDS = ["parcel_id", "owner_name", "legal_description", "sale_date", "available_date",
          "case_number", "opening_bid"]

_BLOCK = re.compile(r"<td>\s*T\.D\.\s*([\d-]+)\s*</td>(.*?)(?=<td>\s*T\.D\.\s*[\d-]+\s*</td>|\Z)", re.S)


def _clean(s: str) -> str:
    s = html.unescape(re.sub(r"<[^>]+>", " ", s))
    return re.sub(r"\s+", " ", s).strip()


def parse_laft(text: str) -> list[dict]:
    """Parse the page. Raises if it doesn't look like the list at all (layout changed)."""
    if "LANDS AVAILABLE FOR TAXES" not in text.upper():
        raise RuntimeError("Putnam page does not look like the Lands Available list "
                           "(layout changed, or you were redirected)")
    rows = []
    for m in _BLOCK.finditer(text):
        case, body = m.group(1), m.group(2)
        owner = re.search(r"<th>(.*?)</th>", body, re.S)
        legal = re.search(r"<td width=425>(.*?)<br>\s*Parcel Number\s*([\d-]+)", body, re.S)
        if not legal:
            continue            # a block we can't read is skipped, never guessed at
        auction = re.search(r"Auction date:\s*<br>\s*([\d/]*)", body)
        avail = re.search(r"Available for Purchase:\s*<br>\s*([\d/]*)", body)
        price = re.search(r"Estimated Purchase Price:\s*<br>\s*\$([\d,\.]+)", body)
        rows.append({
            "parcel_id": legal.group(2),
            "owner_name": _clean(owner.group(1)) if owner else "",
            "legal_description": _clean(legal.group(1)),
            "sale_date": auction.group(1) if auction else "",
            "available_date": avail.group(1) if avail else "",
            "case_number": f"T.D. {case}",
            "opening_bid": price.group(1).replace(",", "") if price else "",
        })
    return rows


def convert(src: Path, dest: Path) -> int:
    """Read the saved HTML at `src`, write a standard CSV at `dest`. Returns the row count."""
    rows = parse_laft(Path(src).read_text(encoding="utf-8", errors="replace"))
    with open(dest, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    return len(rows)
