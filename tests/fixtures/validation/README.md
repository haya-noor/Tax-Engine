# Validation data

Official figures the engine is checked against by `tests/test_wa_official.py`.

## `wa_dor_rates_2026q4.csv`

Combined sales tax rates for 34 Washington cities, copied from the Washington
Department of Revenue (DOR) local rate table for Q4 2026 (Oct 1 to Dec 31, 2026):
https://dor.wa.gov/taxes-rates/sales-use-tax-rates/local-sales-use-tax/local-sales-use-tax-rate-table

Each row also has one ZIP code inside that city. The test looks the ZIP up in the
rate tables and checks the rate matches DOR.

DOR also publishes the full rate list and a ZIP+4 file:
https://dor.wa.gov/taxes-rates/sales-use-tax-rates/downloadable-database

## Collection schedules

DOR publishes a "Retail Sales Tax Collection Schedule" for each rate: a list of
price ranges and the tax due on each. The test copies rows from two of them and
checks the engine gives the same tax:

- 10.0%: https://dor.wa.gov/sites/default/files/2022-02/10.pdf
- 8.9%: https://dor.wa.gov/sites/default/files/2022-02/89.pdf

## Known ZIP-level gaps

A ZIP code can cross city lines, and the ZIP5 table gives one rate per ZIP.
Some ZIPs get the wrong city's rate:

| ZIP | Table says | Real city (DOR rate) |
| --- | --- | --- |
| 98004 | Seattle 10.55% | Bellevue / Clyde Hill 10.30% |
| 98033 | Seattle 10.55% | Kirkland 10.40% |
| 98499 | Tacoma 10.50% | Lakewood 10.30% |

These overcharge when only the ZIP is known. With a street address, the engine
asks DOR for the exact location instead (see `taxengine/wa_dor.py`), and these
addresses get the right rate.
