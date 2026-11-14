# Test fixtures

Small files for the tests only. The real data the engine uses is in `data/`.

- `rates/`: sample files in the layout of the Avalara ZIP5 tables. Only the 60601 and 98101 rows are copied from the real October 2026 table; the others are made up to exercise the code (cross-state ZIPs, leading zeros, layers).
- `wa-dor/`: sample files in the layout of DOR's quarterly downloads. The location codes and rates are real (Q4 2026); the ZIP+4 ranges are made up.
- `validation/`: official DOR figures that `test_washington_official_rates.py` checks the engine against. See its README.
