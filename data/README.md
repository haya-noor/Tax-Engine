Rate tables go here, one folder per source and month, e.g. `avalara-2026-10/`
holding the `TAXRATES_ZIP5_<STATE><YYYYMM>.csv` files from the provider's zip.
The engine reads `data/avalara-2026-10/` by default; set `TAXENGINE_RATES_DIR`
or pass `--rates-dir` to use another folder.
