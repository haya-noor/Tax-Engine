"""Which product categories are taxed in each state.

Each state keeps its rules in its own folder, taxengine/states/<state>/taxability.csv,
one row per category, each with the official source it came from. This module
only reads them; it knows nothing about any one state.
"""

import csv
from dataclasses import dataclass
from pathlib import Path

GENERAL = "general"
SHIPPING = "shipping"


class UnknownCategoryError(LookupError):
    """The product category has no rule for this state."""


@dataclass(frozen=True)
class Rule:
    category: str
    taxable: str        # "yes", "no", or for shipping "proportional"
    description: str
    source: str


# States without a file: general goods and shipping are taxed in full.
DEFAULT_RULES = {
    GENERAL: Rule(GENERAL, "yes", "Physical goods", ""),
    SHIPPING: Rule(SHIPPING, "yes", "Delivery charges", ""),
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
                rule = Rule(rec["category"].strip(), taxable, rec["description"], rec["source"])
                state_rules[rule.category] = rule
        rules[state.upper()] = state_rules
    return rules


def rule_for(rules, state, category):
    state_rules = rules.get(state.upper(), DEFAULT_RULES)
    category = (category or GENERAL).strip().lower()
    if category not in state_rules:
        known = ", ".join(sorted(state_rules))
        raise UnknownCategoryError(f"No {state.upper()} rule for category {category!r}; known: {known}")
    return state_rules[category]
