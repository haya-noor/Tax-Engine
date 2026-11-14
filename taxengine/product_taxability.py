"""Which product categories are taxed in each state.

Rules live in data/taxability/<STATE>.csv, one row per category, each with
the official source it came from. See data/taxability/README.md.
"""

import csv
from dataclasses import dataclass
from pathlib import Path

DEFAULT_TAXABILITY_DIR = Path(__file__).resolve().parent.parent / "data" / "taxability"

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


def load_taxability(directory=DEFAULT_TAXABILITY_DIR):
    """Read every <STATE>.csv into {state: {category: Rule}}."""
    rules = {}
    for path in sorted(Path(directory).glob("*.csv")):
        with open(path, newline="", encoding="utf-8") as f:
            state_rules = {}
            for rec in csv.DictReader(f):
                taxable = rec["taxable"].strip().lower()
                if taxable not in ("yes", "no", "proportional"):
                    raise ValueError(f"{path.name}: taxable must be yes, no or proportional, not {taxable!r}")
                rule = Rule(rec["category"].strip(), taxable, rec["description"], rec["source"])
                state_rules[rule.category] = rule
        rules[path.stem.upper()] = state_rules
    return rules


def rule_for(rules, state, category):
    state_rules = rules.get(state.upper(), DEFAULT_RULES)
    category = (category or GENERAL).strip().lower()
    if category not in state_rules:
        known = ", ".join(sorted(state_rules))
        raise UnknownCategoryError(f"No {state.upper()} rule for category {category!r}; known: {known}")
    return state_rules[category]
