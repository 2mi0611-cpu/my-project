# Tax Deed Deal Finder

Screens tax deed auction lists (or any distressed-property list) for two kinds of deals:

- **Land:** vacant lots you can **build** on, checked for lot size, flood, wetlands, slope, access and zoning.
- **Rehab:** existing houses with a **low renovation cost**. It estimates repairs, after-repair value (ARV), the most you should bid, and the expected profit.

Each property is sorted automatically: if it has a building it's a rehab, otherwise it's land.

For every property it:

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
5. **Rehab math** (houses):
   - Maps the assessor's condition grade (Good / Fair / Poor / Unsound…) to a renovation scope:
     **light** (cosmetic), **medium** (+ kitchen and baths), **heavy** (+ roof and systems) or **gut**.
   - Repair cost = fixed costs + sq ft × your $/sq ft for that scope. It adds extra for houses built
     before 1978 (lead paint) or 1950 (old wiring and plumbing), a contingency (you usually can't see
     inside before a tax sale), and eviction cost if the house is occupied. 3 or more code violations
     raise the scope one level.
   - **Max bid (70% rule)** = ARV × 70% − repairs − closing − quiet title. Don't bid above it.
   - Estimated profit after holding and selling costs, ROI, and gross rent yield if you give a rent figure.
   - Fails anything beyond your maximum scope (default: medium), over your repair cap, below your
     minimum profit, or where the opening bid is already above the max bid.
6. **Reports** a ranked HTML or CSV table, with a map link for each property.
   Use `--strategy land` or `--strategy rehab` to see one kind of deal.

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

Fields: `parcel_id, address, legal_description, owner_name, sale_date, opening_bid, assessed_value,
lot_acres, lot_width_ft, zoning, land_use, improved, road_frontage, lat, lon`, plus for houses:
`building_sqft, year_built, bedrooms, bathrooms, condition, occupied, code_violations, est_arv, est_rent`.

**ARV matters most.** Without an `ARV` column, the tool falls back to assessed value and adds a note
saying so. Assessed value is an as-is value and often far from what a renovated house sells for, so
pull 3–5 sold comps (renovated, similar size, within 0.5 mi, last 6 months) for any house you're
serious about.

**Other distressed lists:** the same import works for pre-foreclosure, probate, code-violation or
wholesaler lists. Put the price you'd pay in a `Price` / `Asking Price` column (read as the opening bid).

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
- Houses: drive by (roof, foundation, boarded windows, fire damage), check the permit history and
  open code cases, and set your renovation $/sq ft from real contractor quotes

## Roadmap

- [ ] County-specific scraper for the first target county
- [ ] Comparable sales for real land values and ARVs (replacing assessed value)
- [ ] Code-violation and permit data from the county/city
- [ ] Rental analysis (rent comps, cash flow, BRRRR)
- [ ] Road frontage from county parcel and road GIS layers
- [ ] Zoning lookup from county GIS
- [ ] Interactive map dashboard
- [ ] Bid and portfolio tracker
