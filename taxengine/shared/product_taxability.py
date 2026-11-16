"""Which product categories are taxed in each state.

Each state keeps its rules in its own folder, taxengine/states/<state>/taxability.csv,
one row per category, each with the official source it came from. This module
only reads them; it knows nothing about any one state.

Every category name comes from an official source, recorded in the basis and
ref columns (see docs/product-categories.md):

    sst        the Streamlined Sales Tax Library of Definitions; ref is its number
    stripe     a Stripe product tax code, for what SST doesn't define; ref is the txcd_ code
    state_law  a state's own law, for what neither defines; ref is the statute
"""

import csv
from dataclasses import dataclass
from pathlib import Path

GENERAL = "general"
NONTAXABLE = "nontaxable"
SHIPPING = "delivery_charges"
BASES = ("sst", "stripe", "state_law")

def canonical_category(category):
    """' Candy ' -> 'candy'; empty -> 'general'."""
    return (category or GENERAL).strip().lower()


class UnknownCategoryError(LookupError):
    """The product category has no rule for this state."""


@dataclass(frozen=True)
class Rule:
    category: str
    taxable: str        # "yes", "no", or for delivery charges "proportional"
    description: str
    source: str
    basis: str = ""     # where the category is defined: sst, stripe or state_law
    ref: str = ""       # its id there: SST number, Stripe tax code, or statute


# States without a file: general goods and delivery charges are taxed in full.
DEFAULT_RULES = {
    GENERAL: Rule(GENERAL, "yes", "Physical goods", "", "stripe", "txcd_99999999"),
    NONTAXABLE: Rule(NONTAXABLE, "no", "Marked as not subject to sales tax", "", "stripe", "txcd_00000000"),
    SHIPPING: Rule(SHIPPING, "yes", "Delivery charges", "", "sst", "11010"),
}


def load_taxability(files):
    """Read {state: path to its taxability.csv} into {state: {category: Rule}}."""
    rules = {}
    for state, path in sorted(files.items()):
        path = Path(path)
        with open(path, newline="", encoding="utf-8") as f:
            state_rules = {}
            for rec in csv.DictReader(f):
                taxable = rec["taxable"].strip().lower()
                if taxable not in ("yes", "no", "proportional"):
                    raise ValueError(f"{path}: taxable must be yes, no or proportional, not {taxable!r}")
                basis = rec["basis"].strip()
                if basis not in BASES:
                    raise ValueError(f"{path}: basis must be one of {', '.join(BASES)}, not {basis!r}")
                rule = Rule(rec["category"].strip(), taxable, rec["description"], rec["source"],
                            basis, rec["ref"].strip())
                state_rules[rule.category] = rule
        rules[state.upper()] = state_rules
    return rules


def rule_for(rules, state, category):
    state_rules = rules.get(state.upper(), DEFAULT_RULES)
    category = canonical_category(category)
    if category not in state_rules:
        known = ", ".join(sorted(state_rules))
        raise UnknownCategoryError(f"No {state.upper()} rule for category {category!r}; known: {known}")
    return state_rules[category]
