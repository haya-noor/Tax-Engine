# Tax Engine

A US sales tax engine. Give it a shipping address and an amount; it returns the
sales tax, broken down by state, county, city and special district.

## What it does

- Looks up the tax rates for an address by ZIP code (state, county, city, special district).
- Taxes only the states you collect in; every other state gets 0 tax.
- Rounds money to the cent, half up, using exact decimals (never floats).
- Records which rate table version was used, so every result can be traced.

Coming next: whole carts (line items, quantities, discounts, shipping) and
product categories that are taxed differently.

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

## Rate data

Rates come from monthly ZIP-code rate tables, one CSV per state, in
`data/<source>-<yyyy-mm>/` (default `data/avalara-2026-10/`). A new month is a
new folder; nothing else changes. Set `TAXENGINE_RATES_DIR` or pass
`--rates-dir` to use another folder. See `data/README.md`.

Things to know about the data:

- ZIPs that cross a state line appear in two states' files; the engine asks for the state instead of guessing.
- No-tax states are included with 0% rates.
- Leading zeros matter (Boston is `02108`); the engine pads ZIPs back to 5 digits.
- One ZIP can cover more than one city or county, so ZIP-based rates can be slightly off. Address-level rates can replace them later.

## Quick start

    python try_it.py 60601 100 --state IL
    python try_it.py 88240 59.99 --state TX
    python try_it.py 60601 100 --state IL --collect-in IL
    python -m unittest -v

No extra libraries are needed (Python 3.10+).

## Project layout

    taxengine/        the engine (no platform code)
    data/             rate tables
    tests/            tests, with small sample rate files in tests/fixtures/
    try_it.py         try it from the command line
