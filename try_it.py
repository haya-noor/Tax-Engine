"""Try the core engine from the command line.

    python try_it.py 10001 100
    python try_it.py 88240 59.99 --state TX
    python try_it.py 60601 100 --state IL --collect-in IL
    python try_it.py 98101 4.50 --state WA --category groceries
    python try_it.py 98004 100 --state WA --street "450 110th Ave NE" --city Bellevue
"""

import argparse
import logging
import sys

from taxengine import DEFAULT_RATES_DIR, Address, CartLine, TaxEngine, WashingtonResolver, calculate_cart


def main():
    parser = argparse.ArgumentParser(description="Look up sales tax by ZIP code")
    parser.add_argument("zip_code")
    parser.add_argument("amount")
    parser.add_argument("--state", help="the address's state; needed for ZIPs that cross a state line")
    parser.add_argument("--category", help="product category, e.g. clothing or groceries (needs --state); "
                                           "see data/taxability/")
    parser.add_argument("--street", help="street address (needs --state); in WA the rate then comes from "
                                         "the Department of Revenue by address instead of the ZIP alone")
    parser.add_argument("--city", default="", help="city, used with --street")
    parser.add_argument("--collect-in", help="states you collect tax in, comma separated (default: all)")
    parser.add_argument("--rates-dir", default=DEFAULT_RATES_DIR, help="folder of TAXRATES_ZIP5_*.csv files")
    args = parser.parse_args()
    logging.basicConfig(format="note: %(message)s")

    collect_in = args.collect_in.split(",") if args.collect_in else None
    try:
        wa = WashingtonResolver.from_files(use_web_lookup=bool(args.street))
        engine = TaxEngine(args.rates_dir, collect_in=collect_in, resolvers={"WA": wa})
    except FileNotFoundError as e:
        sys.exit(f"{e}\nUnzip the rate tables into that folder, or pass --rates-dir.")
    address = None
    if args.street:
        if not args.state:
            sys.exit("--street needs --state")
        address = Address(args.street, args.city, args.state, args.zip_code)
    try:
        if args.category:
            if not args.state:
                sys.exit("--category needs --state, since the rules depend on the state")
            line = CartLine("item", args.amount, category=args.category)
            print(calculate_cart(engine, args.zip_code, args.state, [line], address=address))
        else:
            print(engine.calculate(args.zip_code, args.amount, state=args.state, address=address))
    except (LookupError, ValueError) as e:
        sys.exit(str(e))


if __name__ == "__main__":
    main()
