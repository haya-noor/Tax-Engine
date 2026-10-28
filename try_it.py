"""Try the core engine from the command line.

    python try_it.py 10001 100
    python try_it.py 88240 59.99 --state TX
"""

import argparse

from taxengine import TaxEngine


def main():
    parser = argparse.ArgumentParser(description="Look up sales tax by ZIP code")
    parser.add_argument("zip_code")
    parser.add_argument("amount")
    parser.add_argument("--state", help="needed only for ZIPs that cross a state line")
    args = parser.parse_args()

    engine = TaxEngine()
    print(engine.calculate(args.zip_code, args.amount, state=args.state))


if __name__ == "__main__":
    main()
