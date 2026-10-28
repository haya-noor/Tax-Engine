"""Try the core engine from the command line.

    python try_it.py 10001 100
    python try_it.py 88240 59.99 --state TX
    python try_it.py 60601 100 --state IL --collect-in IL
"""

import argparse
import sys

from taxengine import DEFAULT_RATES_DIR, TaxEngine


def main():
    parser = argparse.ArgumentParser(description="Look up sales tax by ZIP code")
    parser.add_argument("zip_code")
    parser.add_argument("amount")
    parser.add_argument("--state", help="the address's state; needed for ZIPs that cross a state line")
    parser.add_argument("--collect-in", help="states you collect tax in, comma separated (default: all)")
    parser.add_argument("--rates-dir", default=DEFAULT_RATES_DIR, help="folder of TAXRATES_ZIP5_*.csv files")
    args = parser.parse_args()

    collect_in = args.collect_in.split(",") if args.collect_in else None
    try:
        engine = TaxEngine(args.rates_dir, collect_in=collect_in)
    except FileNotFoundError as e:
        sys.exit(f"{e}\nUnzip the rate tables into that folder, or pass --rates-dir.")
    print(engine.calculate(args.zip_code, args.amount, state=args.state))


if __name__ == "__main__":
    main()
