# Target counties (Florida)

Florida sells tax deeds by online auction, run by each county's Clerk or Comptroller.
What follows comes from web search results only. **I have not been able to open any of these
pages from the development environment**, so the exact download links and column layouts are
still unverified. Confirm each one before relying on it.

| County | Who runs the sale | Where the auction runs | Other lists to check |
|---|---|---|---|
| **Volusia** | Clerk of the Circuit Court | volusia.realtaxdeed.com (sales at 9:00 AM ET) | Clerk's "Tax Deeds" page; "Lands Available" page; surplus-funds PDF |
| **Orange** | County Comptroller | orange.realtaxdeed.com (notices say 10:00 AM ET) | Comptroller's tax deed page; legal notices list parcel ID + owner + sale date |
| **Putnam** | Clerk of Court | Clerk's tax deed site (apps.putnam-fl.com), bidders register online | "Tax Deed Sale List and Information" (pick a sale date); county "lands available for taxes" page |
| **Marion** | Clerk of Courts | Clerk's website | **Tax Collector** holds the "Lands Available" list (mariontax.com, Tax Certificate & Deed Sales page) |

## Two kinds of properties to watch

1. **Auction items.** Each sale date has a list of parcels with an opening bid.
2. **Lands available for taxes.** Parcels that got no bid at auction. These are the cheapest
   and least competitive, and they match the "low price" goal best. Ask each county how the
   purchase works and what price applies, because the rules differ.

## How to feed each county into the system

The automatic run (`taxdeed auto`) needs a CSV or Excel file per county. Three ways to get one:

1. **Direct link.** If the county site has a download link (CSV, XLSX), put its URL in `sources.yaml`.
2. **Save by hand.** Export or copy the sale list into a spreadsheet, save it under `data/manual/`,
   and point a `file:` source at it (see `sources.example.yaml`).
3. **A scraper per site.** Needed when the site only offers an interactive page. I can build one
   once I can see the page. Two things are required for that: network access to the host, and a look
   at one real list to match its columns.

Notes from the sources found:
- Putnam's Clerk says bidders need a deposit of **$200 or 5% of their maximum bid** and must
  register on the county's auction platform.
- Marion's Tax Collector says unsold properties go on the **Lands Available** list, held by the
  Tax Collector rather than the Clerk.
- Always confirm dates and rules on the county's own page. Third-party schedules
  (for example taxsaleresources.com) may be out of date.
- The buyer is responsible for finding out which liens survive the sale. Have a Florida real estate
  attorney review your first purchases.
