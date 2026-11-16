# Washington (WA)

Everything specific to Washington. The shared engine is in `taxengine/shared/`.

| File | What it is |
|---|---|
| `__init__.py` | registers the state: its code, rules file and address resolver |
| `address_rates.py` | rates by street address from the Department of Revenue (DOR) |
| `taxability.csv` | which product categories are taxed in Washington |
| `dor-files/` | DOR's quarterly downloads (rates file committed; ZIP+4 file optional) |

## Where the rate comes from

`address_rates.py` tries, in order:

1. the ZIP+4 file in `dor-files/`, when the ZIP has 9 digits (works offline);
2. DOR's address lookup service, when there is a street:
   `https://webgis.dor.wa.gov/webapi/AddressRates.aspx?output=text&addr=...&city=...&zip=...`;
3. the shared ZIP-code tables in `data/`.

## Product taxability: `taxability.csv`

`taxability.csv` says which product categories are taxed in Washington. A product is tagged with one category; untagged products are `general`.

| Column | Meaning |
|---|---|
| `category` | the tag used on products, e.g. `food_and_food_ingredients` |
| `basis` | where the name is defined: `sst`, `stripe` (a Stripe tax code) or `state_law` |
| `ref` | its id there: the SST number, the Stripe `txcd_` code, or the statute |
| `taxable` | `yes` (full local rate), `no` (exempt), or for `delivery_charges` also `proportional` |
| `description` | what the category covers, in plain words |
| `source` | the official page or law the rule comes from |

The `delivery_charges` row says how shipping is taxed. `proportional` means
in the same share as the goods delivered, by price: a box with only food
ships tax-free, a box that is half clothing by price has half its shipping taxed.

Washington is an SST member, so its official answers for each SST category are
in its SST taxability matrix (https://dor.wa.gov/sites/default/files/2022-02/WATaxabilityMatrix.pdf).
These rules were researched from official sources in November 2026 and should
be checked by the client or a tax adviser before going live. States with no
`taxability.csv` tax `general` products and delivery charges in full; any other category raises an error so
nothing is taxed or exempted by guesswork.

## DOR files: `dor-files/`

Put Washington Department of Revenue (DOR) rate files in `dor-files/`, unzipped, to look up rates
by ZIP+4 without the network:

- the rates file from Rates_YYQn.zip: location codes, names and rates. Gives
  readable names such as "Bellevue (1704)".
- the ZIP+4 short file from Zip4QnYYC.zip: ZIP+4 ranges to location codes.

Download them each quarter from
https://dor.wa.gov/taxes-rates/sales-use-tax-rates/downloadable-database

Without these files, Washington rates still come by street address from DOR's
lookup service when it is turned on. See `address_rates.py`.

DOR changes rates each quarter (January 1, April 1, July 1, October 1).
Replace the rates file then; the tax itself comes from the live lookup.
