# Tax engine, step 1: the rate file and the core lookup

## What the client sent

`TAXRATES_ZIP5.zip` is Avalara's free ZIP-code rate table for **October 2026** (the `202610` in each file name). It's now unpacked in `data/avalara-2026-10/`.

- **52 CSV files**, one per state plus DC and Puerto Rico, named like `TAXRATES_ZIP5_CA202610.csv`.
- **40,972 rows** in total, one row per ZIP code.
- One PDF from Avalara explaining the "risk" column (more on that below).

Every CSV has the same 9 columns:

| Column | Meaning | Example (ZIP 60601, Chicago) |
|---|---|---|
| `State` | Two-letter state code | `IL` |
| `ZipCode` | 5-digit ZIP, as text | `60601` |
| `TaxRegionName` | The tax area's name (usually a city, sometimes a district) | `CHICAGO METRO PIER AND EXPOSITION AUTHORITY DISTRICT` |
| `StateRate` | State layer | `0.062500` (6.25%) |
| `EstimatedCountyRate` | County layer | `0.017500` |
| `EstimatedCityRate` | City layer | `0.012500` |
| `EstimatedSpecialRate` | Special districts (transit, stadium, etc.) | `0.012500` |
| `EstimatedCombinedRate` | All four added up: the rate you charge | `0.105000` (10.5%) |
| `RiskLevel` | How risky a ZIP-only rate is | `0` |

Rates are decimals, so `0.0625` means 6.25%.

### Things worth knowing about this data

1. **ZIPs that cross a state line.** 80 ZIPs appear in two states' files. For example `88240` is Hobbs, NM (6.5625%) and Gaines, TX (6.25%). The engine refuses to guess; you pass the state for those.
2. **No-tax states are included with 0% rates**: OR, MT, NH, AK and DE. (AK has local taxes in reality, but this table shows 0.)
3. **The layers sometimes miss the total by 0.0001%** (422 rows, mostly UT and OH, from Avalara's rounding). The engine always charges the combined rate and uses the layers only as the breakdown.
4. **`RiskLevel` is 0 on every row**, so this file doesn't tell us which ZIPs span several cities. The PDF warns that one ZIP can cover more than one city or county, and ZIP-based rates can then be a bit off. That's fine for now; the fix later would be address-level (rooftop) rates.
5. **Leading zeros matter.** Boston is `02108`. If anyone opens these CSVs in Excel and saves them, Excel turns it into `2108`. The engine pads ZIPs back to 5 digits to be safe.
6. **The rates go stale.** Avalara publishes a new table every month. Swapping in a new month's file is just a new folder under `data/`.

## Step 1: the core (done, ready to run)

Given a ZIP and an amount, return the state, county, city, special and combined rates, and the tax. It's pure Python with no extra libraries and no Stripe or Shopify code.

```
tax-engine/
  data/avalara-2026-10/     the client's CSVs (data only)
  taxengine/core.py         the engine
  try_it.py                 try it from the command line
  tests/test_core.py        6 tests
```

How it works, in `taxengine/core.py`:

- `load_rates()` reads all 52 CSVs once into a dictionary keyed by ZIP. It takes about half a second.
- `TaxEngine.calculate(zip, amount, state=None)` finds the row, then works out tax per layer and in total.
- Money uses `Decimal`, never `float`, and rounds to the cent half-up. For example, $50 × 6.25% = $3.125, which rounds to $3.13.

### Run it (PowerShell)

Copy the `tax-engine` folder to your machine, then:

```powershell
cd tax-engine
python try_it.py 10001 100
python try_it.py 88240 59.99 --state TX
python -m unittest -v
```

Example output:

```
ZIP 60601  CHICAGO METRO PIER AND EXPOSITION AUTHORITY DISTRICT, IL
Amount:            100.00
  state        6.25%        6.25
  county       1.75%        1.75
  city         1.25%        1.25
  special      1.25%        1.25
Combined rate:     10.5%
Total tax:          10.50
Grand total:       110.50
```

Or use it from your own code:

```python
from taxengine import TaxEngine
engine = TaxEngine()
result = engine.calculate("98101", "249.00")
print(result.combined_rate, result.total_tax)
```

## The road ahead

1. ✅ **Core lookup**: ZIP + amount → rates + tax
2. **Line items and shipping**: a whole cart (several items, quantities, discounts, shipping), plus rounding per line versus per invoice
3. **Where you collect (nexus)**: only charge tax in states the client is registered in, and charge 0 elsewhere
4. **What's taxable**: a small product-category table (for example, SaaS is taxed in WA and TX but not in CA)
5. **Wire to Stripe**: hook into draft invoices and add tax as a line item (see `build-plan.md`)
6. **Keep rates fresh**: load each month's new table and record which version each invoice used
