# Target counties (Florida): what is verified and what is not

Checked on 2026-11-19 from the development environment. "Verified" means I opened the page and
read the data. Everything else is from web search results and needs checking.

| County | Sale list | Status |
|---|---|---|
| **Putnam** | Clerk's *Lands Available for Taxes* page (apps.putnam-fl.com) | **Works.** 55 parcels read, $1,021 to $20,620, median $1,657. Automated by `sources.florida.yaml`. |
| **Putnam** | Clerk's upcoming *Auction List* | Not automated. It sits behind a disclaimer/session that redirects to the Clerk's home page when requested directly. I did not click through the disclaimer for you. |
| **Volusia** | volusia.realtaxdeed.com (Clerk runs the sale) | **Blocked.** The site's firewall returns 403 to this environment. The Clerk's own pages load, but their lists are not in the HTML I received. |
| **Orange** | orange.realtaxdeed.com (Comptroller runs the sale) | **Blocked** (same 403). |
| **Marion** | Marion County Clerk of the Courts website | **Not opened.** The Tax Collector's page says tax deed sales are processed there. That host is not on this session's allowed list. |

## What the Putnam list does and does not give you

Gives: parcel number, owner, legal description, certificate number, auction date, the date it
becomes available, and the **estimated purchase price**. Properties cannot be bought until 90 days
after the auction, and they are sold "as is", with no warranty, and possibly subject to extra
taxes and fees.

Does not give: address, lot size, zoning, assessed value, flood or wetland data, or road access.
Most entries are old platted subdivision lots ("PUTNAM MANOR S/D BLK 22 LOT 48"). Cheap does not
mean buildable: lots like these often fail on size, septic, flooding or access. That is exactly
what the screening is for, but it needs the missing data. Until then they show as
"can't be ranked". Putnam's own links per parcel (Property Appraiser GIS and Tax Collector pages)
would supply it; those hosts are not on the allowed list yet.

## Florida rules that affect your numbers (from the Volusia Clerk's FAQ)

- **Opening bid** = outstanding tax certificates + delinquent taxes + fees, costs and interest.
- **Deposit:** $200 or 5% of the winning bid, whichever is greater, per property.
- **Payment:** the balance is due within 24 hours of the sale, plus the recording fee, a deposit
  registry fee, and **documentary stamps of $0.70 per $100** of the price. Put this in
  `closing_costs` (about 0.7% of your bid, plus fees).
- **Redemption:** the owner can redeem until the high bidder's full payment arrives.
- **Possession:** the deed holder is entitled to immediate possession (F.S. 197.562).
- **The deed is not a warranty deed.** Sold "as is". The buyer must find out which liens survive.
  Plan for title work, and have a Florida real estate attorney review your first purchases.
- Other counties set their own deposit and timing rules. Confirm each one on its own page.

## How to get the blocked counties working

1. **By hand (works today):** open the county's auction site in your browser, copy the upcoming
   sale list into a spreadsheet, save it under `data/manual/`, and uncomment its source in
   `sources.florida.yaml`. Send me the first 10 rows of one list and I will fill in the `map:` for you.
2. **Automatically:** needs the auction sites to accept the requests. Today they refuse this
   environment. I have not tested GitHub's servers. I will not try to get around a site's block.
