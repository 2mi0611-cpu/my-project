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

## Automatic mode (the one to use)

Set it up once, then it finds the deals for you:

1. `cp sources.example.yaml sources.yaml` and list your county's sale-list download link(s).
   Each source is a direct CSV/XLSX link (or a local file), plus a `map:` of your list's column names.
2. `cp config.example.yaml config.yaml` and set your numbers (repair $/sq ft, target profit, limits).
3. Run `taxdeed auto`. For every source it:
   - downloads the list (the raw file is kept in `data/raw/<source>/<date>`),
   - screens every property on the list data alone (lot size, repair scope, bid vs. value),
   - looks up flood, wetland, slope and address only for the ones that haven't already failed,
   - writes `reports/<date>/shortlist.html` + `.csv` (the best deals) and `all.html` + `.csv`.
4. Properties you've seen before aren't looked up again, and new ones are marked **NEW**.

**The two prices you care about, on every row:**

| | What it means |
|---|---|
| **Ideal bid** | The bid that leaves your **target profit** (default $40k for a house). Aim for this. |
| **Max bid** | The most you should ever bid: the stricter of the 70%-of-ARV rule and your **minimum profit** (default $20k). If the bidding passes this, walk away. |

For land the same two prices come from your value ratios (ideal 40%, max 60% of value, after closing and quiet-title costs).
The run also prints the top 10 with their opening bid, ideal bid, max bid and expected profit.

**Your own numbers:** when you pull sold comps for a property, put the ARV (and rent, condition...) in
`overrides.csv` (see `overrides.example.csv`). It is applied to the matching parcel every run, so a re-download
never erases it.

**Running it on a schedule:** `.github/workflows/daily-scan.yml` runs `taxdeed auto` every morning on GitHub's servers
(which have open internet, so the flood/wetland/elevation lookups work) and saves the reports as a downloadable
"deal-reports" artifact. It starts working once you commit `sources.yaml` and `config.yaml` and the workflow is on your default branch.
On your own computer, a cron line does the same: `0 7 * * * cd ~/my-project && taxdeed auto`.

If a source can't be downloaded (the site needs a login, or returns a web page instead of a spreadsheet) the run
reports that source's error, still processes the others, and exits with an error so a scheduled run shows red.

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

- [ ] County-specific scraper for sites that only offer a search page (needs the target county)
- [ ] Email / text alert when a new deal passes
- [ ] Comparable sales for real land values and ARVs (replacing assessed value)
- [ ] Code-violation and permit data from the county/city
- [ ] Rental analysis (rent comps, cash flow, BRRRR)
- [ ] Road frontage from county parcel and road GIS layers
- [ ] Zoning lookup from county GIS
- [ ] Interactive map dashboard
- [ ] Bid and portfolio tracker
