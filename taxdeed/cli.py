"""Command line:

  taxdeed import  auction.csv --county "Polk" --state FL [--map map.yaml]
  taxdeed enrich  [--county Polk]            # flood, wetlands, slope, geocode
  taxdeed score   [--config config.yaml]
  taxdeed report  --out deals.html [--strategy land|rehab]   # or deals.csv
  taxdeed run     auction.csv --county Polk --state FL --out deals.html   # all of the above
"""
from __future__ import annotations

import argparse
import logging
import sys

import yaml

from .config import load_config
from .db import Store
from .enrich.pipeline import enrich
from .importers.csv_import import import_csv
from .report import write_csv, write_html
from .scoring import score


def _import(args, store):
    cmap = None
    if args.map:
        with open(args.map) as f:
            cmap = yaml.safe_load(f)
    parcels = import_csv(args.csv, county=args.county, state=args.state, column_map=cmap)
    store.upsert(parcels)
    print(f"Imported {len(parcels)} parcels.")


def _enrich(args, store, cfg):
    parcels = store.all(args.county)
    for i, p in enumerate(parcels, 1):
        enrich(p)
        print(f"[{i}/{len(parcels)}] {p.parcel_id}: flood={p.flood_zone} wetlands={p.wetlands} slope={p.slope_pct}")
        store.upsert([p])


def _score(args, store, cfg):
    parcels = [score(p, cfg) for p in store.all(args.county)]
    store.upsert(parcels)
    for strat in ("land", "rehab"):
        group = [p for p in parcels if p.strategy == strat]
        if group:
            counts = {s: sum(p.status == s for p in group) for s in ("PASS", "REVIEW", "FAIL")}
            print(f"Scored {len(group)} {strat} parcels: {counts}")


def _report(args, store):
    parcels = store.all(args.county)
    if args.strategy:
        parcels = [p for p in parcels if p.strategy == args.strategy]
    (write_csv if args.out.endswith(".csv") else write_html)(parcels, args.out, args.strategy)
    print(f"Wrote {args.out} ({len(parcels)} properties)")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="taxdeed")
    ap.add_argument("--db", default="taxdeed.db")
    ap.add_argument("--config", default=None, help="YAML with your criteria (see config.example.yaml)")
    ap.add_argument("-v", "--verbose", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)

    for name in ("import", "run"):
        sp = sub.add_parser(name)
        sp.add_argument("csv")
        sp.add_argument("--county", default="")
        sp.add_argument("--state", default="")
        sp.add_argument("--map", help="YAML mapping our field names -> your CSV headers")
        sp.add_argument("--skip-enrich", action="store_true")
        if name == "run":
            sp.add_argument("--out", default="deals.html")
            sp.add_argument("--strategy", choices=["land", "rehab"], default=None)
    for name in ("enrich", "score", "report"):
        sp = sub.add_parser(name)
        sp.add_argument("--county", default=None)
        if name == "report":
            sp.add_argument("--out", default="deals.html")
            sp.add_argument("--strategy", choices=["land", "rehab"], default=None,
                            help="only vacant land, or only houses to renovate")

    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING)
    cfg = load_config(args.config)
    store = Store(args.db)
    try:
        if args.cmd == "import":
            _import(args, store)
        elif args.cmd == "enrich":
            _enrich(args, store, cfg)
        elif args.cmd == "score":
            _score(args, store, cfg)
        elif args.cmd == "report":
            _report(args, store)
        elif args.cmd == "run":
            _import(args, store)
            args.county = args.county or None
            if not args.skip_enrich:
                _enrich(args, store, cfg)
            _score(args, store, cfg)
            _report(args, store)
    finally:
        store.close()


if __name__ == "__main__":
    sys.exit(main())
