"""Download an auction list from each source in sources.yaml and normalise it to CSV.

A source is either a direct link to a CSV/XLSX file (`url`) or a local file (`file`).
Many county tax collectors publish the sale list as a downloadable spreadsheet; sites
that only show an interactive search page need a county-specific scraper instead.
"""
from __future__ import annotations

import csv
import datetime as dt
import shutil
import time
from pathlib import Path

import requests
import yaml

UA = "taxdeed-screener/0.1"


def load_sources(path: str) -> list[dict]:
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    sources = data.get("sources") or []
    names = set()
    for s in sources:
        if not s.get("name"):
            raise ValueError(f"{path}: every source needs a name")
        if s["name"] in names:
            raise ValueError(f"{path}: duplicate source name {s['name']!r}")
        names.add(s["name"])
        if not (s.get("url") or s.get("file")):
            raise ValueError(f"{path}: source {s['name']!r} needs a url or a file")
    return sources


def _download(url: str, dest: Path, headers: dict | None = None, retries: int = 3) -> None:
    last: Exception | None = None
    for attempt in range(retries):
        try:
            r = requests.get(url, headers={"User-Agent": UA, **(headers or {})}, timeout=60)
            r.raise_for_status()
            dest.write_bytes(r.content)
            return
        except requests.RequestException as e:
            last = e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"download failed after {retries} tries: {url}: {last}")


def _xlsx_to_csv(src: Path, dest: Path, sheet: str | None) -> None:
    try:
        import openpyxl
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("XLSX sources need openpyxl: pip install 'taxdeed[xlsx]'") from e
    wb = openpyxl.load_workbook(src, read_only=True, data_only=True)
    ws = wb[sheet] if sheet else wb.active
    with open(dest, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        for row in ws.iter_rows(values_only=True):
            w.writerow(["" if c is None else c for c in row])
    wb.close()


def _drop_lines(path: Path, n: int) -> None:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
    path.write_text("".join(lines[n:]), encoding="utf-8")


def _validate(path: Path, name: str) -> None:
    head = path.read_bytes()[:2048].lstrip().lower()
    if not head:
        raise RuntimeError(f"{name}: downloaded file is empty")
    if head.startswith((b"<!doctype", b"<html", b"<?xml")):
        raise RuntimeError(f"{name}: got a web page, not a spreadsheet. The site probably needs "
                           "a login or a browser; download the list by hand and use `file:`")


def fetch_source(src: dict, raw_dir: str | Path = "data/raw", today: dt.date | None = None) -> Path:
    """Fetch one source and return the path of a CSV ready for the importer."""
    today = today or dt.date.today()
    name = src["name"]
    out = Path(raw_dir) / name
    out.mkdir(parents=True, exist_ok=True)
    location = src.get("url") or src["file"]
    fmt = (src.get("format") or Path(str(location).split("?")[0]).suffix.lstrip(".") or "csv").lower()
    if fmt in ("xls", "xlsm"):
        fmt = "xlsx"

    raw = out / f"{today.isoformat()}.{fmt}"
    if src.get("url"):
        _download(src["url"], raw, src.get("headers"))
    else:
        shutil.copyfile(src["file"], raw)

    if fmt == "xlsx":
        csv_path = out / f"{today.isoformat()}.csv"
        _xlsx_to_csv(raw, csv_path, src.get("sheet"))
    elif fmt == "csv":
        csv_path = raw
    else:
        raise ValueError(f"{name}: unsupported format {fmt!r} (use csv or xlsx)")

    _validate(csv_path, name)
    if src.get("skip_rows"):
        _drop_lines(csv_path, int(src["skip_rows"]))
    return csv_path
