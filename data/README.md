# Data shared by all states

## Rate tables: `avalara-YYYY-MM/`

One folder per source and month, holding the `TAXRATES_ZIP5_<STATE><YYYYMM>.csv`
files from the provider's zip. The engine reads `data/avalara-2026-10/` by
default; set `TAXENGINE_RATES_DIR` or pass `--rates-dir` to use another folder.

These ZIP-code tables cover every state. The engine uses them for states with
no address source of their own, and as the backup when a state's source can't
answer. State-specific data lives in `taxengine/states/<state>/`.
