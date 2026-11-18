# Tax Deed Deal Finder

Screens tax deed auction lists for **buildable** parcels and ranks them by value.

For every parcel on an auction list it:

1. **Imports** the county's list (CSV; common header names are recognized automatically).
2. **Enriches** it with free federal data:
   - FEMA flood zone (National Flood Hazard Layer)
   - Mapped wetlands (U.S. Fish & Wildlife National Wetlands Inventory)
   - Elevation and estimated slope (USGS Elevation Point Query Service)
   - Coordinates from the street address (U.S. Census geocoder), if the list has no lat/lon
3. **Checks buildability**: lot size, lot width, flood zone, wetlands, slope, road frontage, zoning and vacancy, using rules you set.
   - `PASS`: every check passed.
   - `FAIL`: a hard check failed.
   - `REVIEW`: nothing failed, but some data is missing.
4. **Scores the deal (0–100)** from total cost (bid + closing + quiet title) compared with estimated value. The score is cut for failed checks and for red flags such as "common area", "drainage", "easement", sliver lots, or no address.
5. **Reports** a ranked HTML or CSV table, with a map link for each parcel.

## Quick start

```bash
pip install -e ".[dev]"
cp config.example.yaml config.yaml        # set your criteria
taxdeed --config config.yaml run sample_data/sample_auction.csv \
        --county "Sample" --state FL --out deals.html
open deals.html
```

Steps can also run separately: `taxdeed import`, `taxdeed enrich`, `taxdeed score`, `taxdeed report`.
Data is kept in `taxdeed.db` (SQLite), so you can re-score with new criteria without fetching the data again.

### Your county's CSV

The importer recognizes headers like `Parcel Number`, `APN`, `Folio`, `Minimum Bid`, `Acres`,
`Latitude`, and so on. If your county uses different names, write a small YAML map and pass `--map`:

```yaml
parcel_id: "Account #"
opening_bid: "Opening Bid Amt"
lot_acres: "Land Area (AC)"
```

Fields: `parcel_id, address, legal_description, sale_date, opening_bid, assessed_value,
lot_acres, lot_width_ft, zoning, land_use, improved, road_frontage, lat, lon`.

Vacant tax-deed lots often have no street address. Add lat/lon from the county GIS viewer
so that the flood, wetland and slope checks can run.

## Limits

This is a **screening tool**. It narrows a 500-parcel list down to the 20 worth researching.
Before bidding on anything, still check:
- Title search: surviving liens, IRS liens, municipal code liens, HOA
- Zoning and minimum-lot rules with the county planning department
- Road access in person (frontage data in auction lists is often wrong)
- Wetlands: NWI maps are approximate, and only a field delineation decides
- Utilities: water and sewer availability, or septic and well feasibility (perc test)
- Your state's redemption period and quiet-title process

## Roadmap

- [ ] County-specific scraper for the first target county
- [ ] Comparable land sales for real market values (replacing assessed value)
- [ ] Road frontage from county parcel and road GIS layers
- [ ] Zoning lookup from county GIS
- [ ] Interactive map dashboard
- [ ] Bid and portfolio tracker
