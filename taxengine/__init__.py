"""A US sales tax engine: address in, tax out.

    shared/   what every state uses (rates by ZIP, the calculation, carts)
    states/   one folder per state (its product rules, its own rate source)
"""

from .shared.tax_calculator import (
    DEFAULT_RATES_DIR,
    Address,
    AmbiguousZipError,
    TaxEngine,
    TaxResult,
    UnknownZipError,
    load_rates,
    money,
    normalize_zip,
)
from .shared.cart_tax import CartLine, CartResult, calculate_cart
from .shared.product_taxability import UnknownCategoryError, load_taxability
from .states import address_resolvers, taxability_files
from .states.washington import WashingtonResolver

__all__ = [
    "Address",
    "AmbiguousZipError",
    "CartLine",
    "CartResult",
    "DEFAULT_RATES_DIR",
    "TaxEngine",
    "TaxResult",
    "UnknownCategoryError",
    "UnknownZipError",
    "WashingtonResolver",
    "address_resolvers",
    "calculate_cart",
    "load_rates",
    "load_taxability",
    "money",
    "normalize_zip",
    "taxability_files",
]
