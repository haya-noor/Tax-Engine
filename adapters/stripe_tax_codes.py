"""Stripe product tax codes (txcd_...) -> the engine's SST-based categories.

A business may already have tax codes on its Stripe products. When a product has
no "tax_category" metadata, its tax code decides the category. Codes not listed
here fall back to "general" (taxed), so the engine never under-collects by guessing.
Only codes that match an SST definition are listed; Stripe codes with no SST
equivalent (SaaS, "Nontaxable", ...) are taxed as general.

Only codes checked against Stripe's list are here: https://docs.stripe.com/tax/tax-codes
Food, candy, drinks and delivery codes still need checking before they are added;
until then those products need "tax_category" metadata.
"""

from taxengine.shared.product_taxability import GENERAL

STRIPE_TAX_CODES = {
    "txcd_99999999": GENERAL,                           # General - Tangible Goods
    "txcd_30011000": "clothing",                        # Clothing and Footwear
    "txcd_32020001": "prescription_drugs",              # Prescription Drugs
    "txcd_32020002": "over_the_counter_drugs",          # Drugs - Over the Counter
    "txcd_10302000": "digital_books",                   # Digital Books - downloaded, permanent rights
    "txcd_10401100": "digital_audio_works",             # Digital Audio Works
    "txcd_10402100": "digital_audio_visual_works",      # Digital Audio Visual Works
    "txcd_10202000": "prewritten_software_electronic",  # Downloadable Software - personal use
    "txcd_10202003": "prewritten_software_electronic",  # Downloadable Software - business use
}


def category_for_tax_code(tax_code):
    """'txcd_30011000' -> 'clothing'; None or an unlisted code -> 'general'."""
    if isinstance(tax_code, dict):      # an expanded tax_code object
        tax_code = tax_code.get("id")
    return STRIPE_TAX_CODES.get(tax_code or "", GENERAL)
