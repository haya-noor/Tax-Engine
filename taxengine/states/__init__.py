"""One folder per state, for everything that is specific to that state.

A state folder holds:
- taxability.csv: which product categories are taxed there (required once we
  collect in that state; without it, general goods and shipping are taxed in full);
- optionally an address resolver: code that finds the exact rate for a street
  address from the state's own source, with its data files.

To add a state, make its folder like washington/ and add it to STATES below.
"""

from . import washington

# State code -> its package. Each package has STATE, TAXABILITY_FILE and
# optionally address_resolver(use_web_lookup).
STATES = {washington.STATE: washington}


def taxability_files():
    """{state: path} for every state folder that has a taxability.csv."""
    return {code: s.TAXABILITY_FILE for code, s in STATES.items() if s.TAXABILITY_FILE.exists()}


def address_resolvers(use_web_lookup=False):
    """{state: resolver} for every state that can look up rates by street address."""
    return {code: s.address_resolver(use_web_lookup) for code, s in STATES.items()
            if hasattr(s, "address_resolver")}
