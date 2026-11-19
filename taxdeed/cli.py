"""Command line:

  taxdeed serve   [--port 8765] [--open]     # the local web interface
  taxdeed auto    [--sources sources.yaml]   # download every source, screen, write the shortlist
  taxdeed fetch   [--sources sources.yaml]   # just download the lists
  taxdeed import  auction.csv --county "Polk" --state FL [--map map.yaml]
  taxdeed enrich  [--county Polk]            # flood, wetlands, slope, geocode
  taxdeed score
  taxdeed report  --out deals.html [--strategy land|rehab]   # or deals.csv
  taxdeed run     auction.csv --county Polk --state FL --out deals.html   # one file, all steps
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import os
import sys

import yaml

from . import auto
from .config import load_config
from .db import Store
from .enrich.pipeline import enrich
from .fetch import fetch_source, load_sources
from .importers.csv_import import import_csv
from .report import usd, write_csv, write_html
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


def _fetch(args):
    bad = 0
    for src in load_sources(args.sources):
        if args.only and src["name"] not in args.only:
            continue
        try:
            print(f"{src['name']}: {fetch_source(src, args.raw_dir, dt.date.today())}")
        except Exception as e:  # noqa: BLE001
            bad += 1
            print(f"{src['name']}: FAILED - {e}", file=sys.stderr)
    return 1 if bad else 0


def _m(v):
    return "n/a" if v is None else usd(v)


def _serve(args, cfg):
    from .web import make_server
    if not os.path.exists(args.db):
        print(f"No database at {args.db} yet. Run `taxdeed auto` first; the page will be empty until then.")
    srv = make_server(args.db, cfg, args.ui_overrides, args.host, args.port)
    url = f"http://{args.host}:{srv.server_address[1]}/"
    print(f"Open {url}   (Ctrl+C to stop)")
    if args.open:
        import webbrowser
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        srv.server_close()
    return 0


def _auto(args, store, cfg):
    res = auto.run(cfg, store, sources_path=args.sources, overrides_path=args.overrides,
                   ui_overrides_path=args.ui_overrides,
                   out_root=args.out_dir, only=args.only, skip_enrich=args.skip_enrich,
                   raw_dir=args.raw_dir)
    print(f"{res['total']} properties from {res['sources_ok']} source(s), {res['new']} new, "
          f"{len(res['shortlist'])} on the shortlist.")
    if res["unvalued"]:
        print(f"{res['unvalued']} properties have no value data (assessed value or ARV), so they can't "
              f"be ranked. They are in all.html; add values in overrides.csv.")
    print(f"Open {res['out_dir']}/shortlist.html\n")
    for i, p in enumerate(res["shortlist"][:10], 1):
        print(f"{i:>2}. {'NEW ' if p.is_new else ''}{p.address or p.parcel_id} "
              f"[{p.strategy}, {p.status}, score {p.deal_score}]\n"
              f"      opening {_m(p.opening_bid)}   ideal bid {_m(p.ideal_bid)}   "
              f"max bid {_m(p.max_bid)}   est. profit {_m(p.est_profit)}")
    for name, err in res["errors"].items():
        print(f"! {name}: {err}", file=sys.stderr)
    return 1 if res["errors"] else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="taxdeed")
    ap.add_argument("--db", default="taxdeed.db")
    ap.add_argument("--config", default=None,
                    help="YAML with your criteria (default: config.yaml if present; see config.example.yaml)")
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
    for name in ("fetch", "auto"):
        sp = sub.add_parser(name)
        sp.add_argument("--sources", default="sources.yaml")
        sp.add_argument("--only", nargs="*", help="only these source names")
        sp.add_argument("--raw-dir", default="data/raw")
        if name == "auto":
            sp.add_argument("--overrides", default="overrides.csv",
                            help="CSV of your own figures per parcel (ARV, rent, condition...)")
            sp.add_argument("--ui-overrides", default="overrides.ui.csv",
                            help="values saved from the web interface")
            sp.add_argument("--skip-enrich", action="store_true")
            sp.add_argument("--out-dir", default=None)

    sp = sub.add_parser("serve", help="open the local web interface")
    sp.add_argument("--host", default="127.0.0.1", help="keep 127.0.0.1 so only this computer can connect")
    sp.add_argument("--port", type=int, default=8765)
    sp.add_argument("--open", action="store_true", help="open it in your browser")
    sp.add_argument("--ui-overrides", default="overrides.ui.csv")

    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING)
    cfg_path = args.config or ("config.yaml" if os.path.exists("config.yaml") else None)
    cfg = load_config(cfg_path)

    if args.cmd == "fetch":
        return _fetch(args)
    if args.cmd == "serve":
        return _serve(args, cfg)
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
        elif args.cmd == "auto":
            return _auto(args, store, cfg)
        elif args.cmd == "run":
            _import(args, store)
            args.county = args.county or None
            if not args.skip_enrich:
                _enrich(args, store, cfg)
            _score(args, store, cfg)
            _report(args, store)
    finally:
        store.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
