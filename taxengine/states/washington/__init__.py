"""Washington (WA): product rules and rates by street address from the
Washington State Department of Revenue (DOR). See README.md in this folder."""

from pathlib import Path

from .address_rates import WashingtonResolver

STATE = "WA"
TAXABILITY_FILE = Path(__file__).resolve().parent / "taxability.csv"


def address_resolver(use_web_lookup=False):
    """DOR rates by address: the web lookup when use_web_lookup, plus the files in dor-files/."""
    return WashingtonResolver.from_files(use_web_lookup=use_web_lookup)
