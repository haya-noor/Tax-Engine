# Data

## Rate tables: `avalara-YYYY-MM/`

One folder per source and month, holding the `TAXRATES_ZIP5_<STATE><YYYYMM>.csv`
files from the provider's zip. The engine reads `data/avalara-2026-10/` by
default; set `TAXENGINE_RATES_DIR` or pass `--rates-dir` to use another folder.

## Product taxability: `taxability/`

Each file (`WA.csv`, ...) says which product categories are taxed in that
state. A product is tagged with one category; untagged products are `general`.

| Column | Meaning |
|---|---|
| `category` | the tag used on products, e.g. `groceries` |
| `taxable` | `yes` (full local rate), `no` (exempt), or for `shipping` also `proportional` |
| `description` | what the category covers, in plain words |
| `source` | the official page or law the rule comes from |

The `shipping` row says how delivery charges are taxed. `proportional` means
in the same share as the goods delivered, by price: a box with only groceries
ships tax-free, a box that is half clothing by price has half its shipping taxed.

These rules were researched from official sources in November 2026 and should
be checked by the client or a tax adviser before going live. States with no
file here tax `general` products and shipping in full; any other category raises an error so
nothing is taxed or exempted by guesswork.

## Washington DOR files: `wa-dor/`

Put Washington Department of Revenue rate files here, unzipped, to look up rates
by ZIP+4 without the network:

- the rates file from Rates_YYQn.zip: location codes, names and rates. Gives
  readable names such as "Bellevue (1704)".
- the ZIP+4 short file from Zip4QnYYC.zip: ZIP+4 ranges to location codes.

Download them each quarter from
https://dor.wa.gov/taxes-rates/sales-use-tax-rates/downloadable-database

Without these files, Washington rates still come by street address from DOR's
lookup service when it is turned on. See `taxengine/wa_dor.py`.
