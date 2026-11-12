# Tax Engine

A US sales tax engine. Give it a shipping address and a cart; it returns the
sales tax for each line, broken down by state, county, city and special district.

## What it does

- Looks up the tax rates for an address by ZIP code (state, county, city, special district).
- Taxes only the states you collect in; every other state gets 0 tax.
- Taxes a whole cart: line items, quantities, discounts and shipping.
- Applies each state's product rules by category (e.g. in Washington groceries
  are exempt and clothing is taxed). Washington is the first state with rules.
- Rounds money to the cent, half up, per line, using exact decimals (never floats).
- Records which rate table version was used, so every result can be traced.

## How it fits into other systems

The engine has one input format and one output format, and knows nothing about
who is calling it. Any checkout, invoicing or billing system can use it by
converting its order into the engine's input and reading the result back.

    your system  ->  adapter  ->  Tax Engine  ->  tax result  ->  adapter  ->  your system

Adapters live outside the `taxengine` package, so adding one never changes the
tax logic.

## Use it from code

```python
from taxengine import TaxEngine

engine = TaxEngine(collect_in={"IL"})          # omit collect_in to tax every state
result = engine.calculate("60601", "100.00", state="IL")

result.total_tax       # Decimal("10.50")
result.combined_rate   # Decimal("0.105")
result.layers          # tax per layer: state, county, city, special
result.rate_version    # "avalara-2026-10"
```

**Input:** ZIP code, amount, and the address's state. The state is needed for
the ~80 ZIPs that cross a state line, and to give 0 tax outside the states you
collect in.

**Output:** a `TaxResult` with the combined rate, total tax, the tax for each
layer, and the rate table version. The total always uses the combined rate; the
layers are the breakdown.

### A whole cart

```python
from taxengine import CartLine, TaxEngine, calculate_cart

engine = TaxEngine(collect_in={"WA"})
cart = calculate_cart(engine, "98101", "WA", [
    CartLine("shirt", "25.00", quantity=2, discount="5.00", category="clothing"),
    CartLine("bread", "5.00", category="groceries"),
], shipping="8.00")

cart.total_tax   # Decimal("5.51"): shirt 4.75 + bread 0 + shipping 0.76
cart.lines       # per line: category, taxed or exempt, and its TaxResult
```

Each line is taxed and rounded on its own. Shipping follows the state's rule;
in Washington it is taxed in the same share as the goods (here 90% of the
goods by price are taxable, so 90% of the shipping is).

## Product categories

Which products are taxed is set per state in `data/taxability/<STATE>.csv`,
one row per category, each with the official source it comes from. Products
without a category are `general`. Washington's file covers:

| Category | Taxed in WA? |
|---|---|
| `general`, `clothing` | yes |
| `groceries` (incl. candy) | no |
| `prepared_food`, `soft_drinks`, `bottled_water` | yes |
| `dietary_supplements`, `otc_drugs` (no prescription) | yes |
| `prescription_drugs`, `newspapers` | no |
| `digital_goods`, `software` (incl. SaaS) | yes |
| `shipping` | in proportion to taxed goods |

An unknown category is an error, never a guess. States without a file tax
`general` products and shipping only. See `data/taxability/README.md`. These
rules should be checked by the client or a tax adviser before going live.

## Adapters

Adapters live in `adapters/` and only translate; the tax logic stays in
`taxengine/`.

### Stripe invoices (test mode)

`adapters/stripe_invoices.py` adds the engine's tax to a draft Stripe invoice,
one tax line per layer, using Stripe's
[manual tax amounts](https://docs.stripe.com/invoicing/taxes/manual-tax-amounts).
It taxes the shipping address, or the billing address if there is none, on
each line's amount after discounts. Each invoice item's product category comes
from its metadata, e.g. `tax_category=groceries`; items with
`tax_category=shipping` are delivery charges.

    pip install -r requirements-stripe.txt
    $env:STRIPE_SECRET_KEY = "sk_test_..."     # PowerShell; Stripe Dashboard > Developers > API keys, test mode
    python stripe_demo.py                                # Seattle: T-shirt, bread, ebook, shipping
    python stripe_demo.py --item "Hoodie=59.99:clothing" --item "Bread=4.50:groceries" --shipping 8.00

The demo creates a customer, a draft invoice with the items, adds our tax,
finalizes it, and prints links to the invoice. Only test keys are accepted.

`stripe_webhook.py` does it automatically, the way a tax app does. Stripe tells
it whenever a draft invoice is created (for example a subscription renewal) or
an item on a draft is added, changed or removed, and it recalculates that
invoice's tax. So an invoice you build in the Dashboard already has its tax
when you press Send. Tax only changes on drafts; sent invoices are left alone.

Try it on your computer (in two PowerShell windows, both with STRIPE_SECRET_KEY set):

    stripe listen --api-key $env:STRIPE_SECRET_KEY --events invoice.created,invoice.updated,invoiceitem.created,invoiceitem.deleted --forward-to localhost:4242/webhook
    # it prints a whsec_... secret
    $env:STRIPE_WEBHOOK_SECRET = "whsec_..."
    python stripe_webhook.py

To run it all the time, host it: `render.yaml` sets it up on Render, and
[docs/hosting.md](docs/hosting.md) walks through it, including registering the
webhook in the Stripe Dashboard. Any server that runs Python works (set
`HOST=0.0.0.0`, `PORT`, `STRIPE_SECRET_KEY` and `STRIPE_WEBHOOK_SECRET`).

### Monthly report

Each invoice the engine taxes keeps a small record in its metadata (keys starting
`tax_engine_`): the DOR location code, gross and taxable sales, and the state and
local tax. `tax_report.py` adds them up for a month, per location code, which is
what Washington's excise tax return asks for:

    python tax_report.py 2026-11                  # print the table
    python tax_report.py 2026-11 --csv nov.csv    # also save a CSV

An invoice counts in the month it was finalized; drafts and voided invoices are
left out. Invoices taxed before this record existed are listed separately.
Check the figures before filing.

## Rate data

Rates come from monthly ZIP-code rate tables, one CSV per state, in
`data/<source>-<yyyy-mm>/` (default `data/avalara-2026-10/`). A new month is a
new folder; nothing else changes. Set `TAXENGINE_RATES_DIR` or pass
`--rates-dir` to use another folder. See `data/README.md`.

Things to know about the data:

- ZIPs that cross a state line appear in two states' files; the engine asks for the state instead of guessing.
- No-tax states are included with 0% rates.
- Leading zeros matter (Boston is `02108`); the engine pads ZIPs back to 5 digits.
- One ZIP can cover more than one city or county, so a ZIP-based rate can be the wrong city's. For
  Washington, rates by street address fix this (next section).

## Rates by street address

A state can have a resolver that finds the rate from the full address. When it
finds one, that rate is used; otherwise the engine falls back to the ZIP table.

```python
from taxengine import Address, TaxEngine, WashingtonResolver

wa = WashingtonResolver.from_files(use_web_lookup=True)
engine = TaxEngine(collect_in={"WA"}, resolvers={"WA": wa})
home = Address("450 110th Ave NE", "Bellevue", "WA", "98004")
engine.calculate("98004", "100", "WA", address=home).total_tax   # 10.30, Bellevue; the ZIP alone gives Seattle's 10.55
```

Washington's resolver uses the Department of Revenue (DOR) in this order:

1. the quarterly ZIP+4 file, when the ZIP has 9 digits and the file is in `data/wa-dor/`;
2. DOR's [address lookup service](https://dor.wa.gov/wa-sales-tax-rate-lookup-url-interface), when there is a street (needs the network);
3. the ZIP table.

The result's `source` says which was used (`dor-zip4`, `dor-address` or `zip5`).
A failed lookup logs a warning. `calculate_cart` takes the same `address=`, and
the Stripe adapter passes the invoice's street address. The Stripe demo and
webhook turn the DOR lookup on (`--no-dor-lookup` or `TAXENGINE_DOR_LOOKUP=0`
turns it off).

## Quick start

    python try_it.py 60601 100 --state IL
    python try_it.py 88240 59.99 --state TX
    python try_it.py 60601 100 --state IL --collect-in IL
    python try_it.py 98101 4.50 --state WA --category groceries
    python try_it.py 98004 100 --state WA --street "450 110th Ave NE" --city Bellevue
    python -m unittest -v

No extra libraries are needed (Python 3.10+).

## Project layout

    taxengine/        the engine (no platform code): core.py, cart.py, taxability.py,
                      wa_dor.py (Washington rates by address)
    adapters/         connections to other systems (Stripe so far)
    data/             rate tables, and product rules per state in data/taxability/
                      official figures to check against in data/validation/
                      optional Washington DOR files in data/wa-dor/
    tests/            tests, with small sample rate files in tests/fixtures/
    try_it.py         try it from the command line
    stripe_demo.py    make a Stripe test invoice with our tax
    stripe_webhook.py add our tax to new Stripe invoices automatically
    tax_report.py     monthly tax report per location, from Stripe invoices
    render.yaml       hosting setup for the webhook (see docs/hosting.md)
