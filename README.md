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

`adapters/stripe_invoice_tax.py` adds the engine's tax to a draft Stripe invoice,
one tax line per layer, using Stripe's
[manual tax amounts](https://docs.stripe.com/invoicing/taxes/manual-tax-amounts).
It taxes the shipping address, or the billing address if there is none, on
each line's amount after discounts. Each invoice item's product category comes
from its metadata, e.g. `tax_category=groceries`; items with
`tax_category=shipping` are delivery charges.

`stripe_tax_webhook.py` does this automatically, the way a tax app does. Stripe tells
it whenever a draft invoice is created (for example a subscription renewal) or
an item on a draft is added, changed or removed, and it recalculates that
invoice's tax. So an invoice you build in the Dashboard already has its tax
when you press Send. Tax only changes on drafts; sent invoices are left alone.

Try it on your computer (in two PowerShell windows, both with STRIPE_SECRET_KEY
set to a test key, `sk_test_...`):

    pip install -r requirements.txt
    stripe listen --api-key $env:STRIPE_SECRET_KEY --events invoice.created,invoice.updated,invoiceitem.created,invoiceitem.deleted --forward-to localhost:4242/webhook
    # it prints a whsec_... secret
    $env:STRIPE_WEBHOOK_SECRET = "whsec_..."
    python stripe_tax_webhook.py

To run it all the time, host it on Vercel (`api/vercel_handler.py`, `vercel.json`):
[docs/hosting.md](docs/hosting.md) walks through it, including registering the
webhook in the Stripe Dashboard. Any server that runs Python also works (set
`HOST=0.0.0.0`, `PORT`, `STRIPE_SECRET_KEY` and `STRIPE_WEBHOOK_SECRET`).

### Monthly report

Each invoice the engine taxes keeps a small record in its metadata (keys starting
`tax_engine_`): the DOR location code, gross and taxable sales, and the state and
local tax. `monthly_tax_report.py` adds them up for a month, per location code, which is
what Washington's excise tax return asks for:

    python monthly_tax_report.py 2026-11                  # print the table
    python monthly_tax_report.py 2026-11 --csv nov.csv    # also save a CSV

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
the Stripe adapter passes the invoice's street address. The webhook turns the
DOR lookup on (`TAXENGINE_DOR_LOOKUP=0` turns it off).

## Quick start

    python calculate_tax.py 60601 100 --state IL
    python calculate_tax.py 88240 59.99 --state TX
    python calculate_tax.py 60601 100 --state IL --collect-in IL
    python calculate_tax.py 98101 4.50 --state WA --category groceries
    python calculate_tax.py 98004 100 --state WA --street "450 110th Ave NE" --city Bellevue
    python -m unittest -v

The engine needs no extra libraries (Python 3.10+); the Stripe parts need
`pip install -r requirements.txt`.

## Project layout

    calculate_tax.py          work out the tax for a ZIP or address from the command line
    stripe_tax_webhook.py     add our tax to Stripe invoices automatically
    monthly_tax_report.py     monthly tax report per location, from Stripe invoices
    api/vercel_handler.py     runs the webhook on Vercel, with vercel.json (see docs/hosting.md)

    taxengine/                the engine (no platform code)
      tax_calculator.py         rate lookup by ZIP and the tax calculation
      cart_tax.py               tax for a whole cart: lines, discounts, shipping
      product_taxability.py     which product categories are taxed in each state
      washington_address_rates.py  Washington rates by street address, from DOR
    adapters/                 connections to other systems
      stripe_invoice_tax.py     puts the engine's tax on Stripe invoices
      stripe_monthly_report.py  totals the taxed Stripe invoices for a month
    data/                     rate tables, product rules, Washington DOR files (see data/README.md)
    tests/                    tests, with small sample files in tests/fixtures/ automatically
    api/, vercel.json run the webhook on Vercel (see docs/hosting.md)
    monthly_tax_report.py     monthly tax report per location, from Stripe invoices
