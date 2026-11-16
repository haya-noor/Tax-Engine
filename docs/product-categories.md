# Product categories

Each product gets one category, and each state's `taxability.csv` says whether
that category is taxed there. This page explains where the category names come
from, how a product's category is found, and how to add a state.

## Where the names come from

Every category name comes from an official source. Nothing is invented. The
source is recorded in each row's `basis` and `ref` columns.

| Basis | Used for | `ref` holds | Example |
|---|---|---|---|
| `sst` | Anything the [Streamlined Sales Tax](https://www.streamlinedsalestax.org/) Library of Definitions defines. This is always tried first. | the SST reference number | `candy`, ref `40010` |
| `stripe` | Things SST does not define, using [Stripe's product tax codes](https://docs.stripe.com/tax/tax-codes) | the Stripe tax code | `software_as_a_service`, ref `txcd_10103000` |
| `state_law` | Things neither SST nor Stripe defines | the statute | `printed_newspapers`, ref `RCW 82.08.0253` |

This mirrors how the big tax engines work. Avalara, TaxJar and Stripe Tax each
keep their own official code list and map every code to each state's rules,
with SST definitions as the base for SST states.

A name that is not in the state's file, such as `groceries`, is refused with an
error. The engine never guesses.

## How a product's category is found

When the engine taxes a Stripe invoice line, it checks these in order:

1. `tax_category` metadata on the invoice line.
2. `tax_category` metadata on the invoice item the line came from.
3. `tax_category` metadata on the product.
4. The product's Stripe tax code, turned into a category by
   `adapters/stripe_tax_codes.py`. For example, `txcd_30011000` (Clothing)
   becomes `clothing`.
5. Otherwise the product is `general`, and it is taxed.

Step 5 matches the other engines. An item with no category is taxed as general
goods, because tax charged by mistake can be refunded, but tax that was not
charged becomes the business's debt. A Stripe tax code that isn't in the list
is also treated as `general`.

To set a category in the Stripe Dashboard, open the product, go to Metadata,
and add the key `tax_category` with a category name from the table below.
Alternatively, give the product a Stripe tax code that is in the list.

## Washington

From `taxengine/states/washington/taxability.csv`:

| Category | Basis | Ref | Taxed in WA? |
|---|---|---|---|
| `general` | stripe | txcd_99999999 | yes |
| `clothing` | sst | 20010 | yes |
| `food_and_food_ingredients` | sst | 40030 | no |
| `candy` | sst | 40010 | no |
| `prepared_food` | sst | 41000 | yes |
| `soft_drinks` | sst | 40050 | yes |
| `bottled_water` | sst | 40060 | yes |
| `dietary_supplements` | sst | 40020 | yes |
| `prescription_drugs` | sst | 51020 | no |
| `over_the_counter_drugs` | sst | 51130 | yes |
| `digital_products` | sst | 31000 | yes |
| `digital_audio_visual_works` | sst | 31040 | yes |
| `digital_audio_works` | sst | 31070 | yes |
| `digital_books` | sst | 31100 | yes |
| `prewritten_software` | sst | 30040 | yes |
| `prewritten_software_electronic` | sst | 30050 | yes |
| `nontaxable` | stripe | txcd_00000000 | no |
| `software_as_a_service` | stripe | txcd_10103000 | yes |
| `digital_newspapers` | stripe | txcd_10304000 | no, if it is the electronic edition of a printed paper |
| `printed_newspapers` | state_law | RCW 82.08.0253 | no |
| `delivery_charges` | sst | 11010 | in the same share as the taxed goods |

Each row also has a description and a link to its official source.

States with no file yet tax `general` and `delivery_charges`, and exempt
`nontaxable`. Any other category is an error there.

## Stripe tax codes the engine understands

| Stripe tax code | Category |
|---|---|
| txcd_99999999 General - Tangible Goods | `general` |
| txcd_00000000 Nontaxable | `nontaxable` |
| txcd_30011000 Clothing and Footwear | `clothing` |
| txcd_32020001 Prescription Drugs | `prescription_drugs` |
| txcd_32020002 Drugs - Over the Counter | `over_the_counter_drugs` |
| txcd_10302000 Digital Books | `digital_books` |
| txcd_10401100 Digital Audio Works | `digital_audio_works` |
| txcd_10402100 Digital Audio Visual Works | `digital_audio_visual_works` |
| txcd_10202000, txcd_10202003 Downloadable Software | `prewritten_software_electronic` |
| txcd_10103000, 10103001, 10103100, 10103101 SaaS | `software_as_a_service` |
| txcd_10304000 to txcd_10304102 Digital Newspapers | `digital_newspapers` |

The codes for food, candy, drinks and delivery are not in this list yet,
because they still need checking against Stripe's list. Until they are added,
give those products `tax_category` metadata.

## Adding a state

1. Make a folder `taxengine/states/<state>/` with a `taxability.csv` that has
   the same columns.
2. For an SST state, fill in the `sst` rows from that state's SST taxability
   matrix. The matrix is free and public, on the SST website and usually as a
   PDF on the state's tax department site. It gives taxable or exempt for each
   SST reference number. Use the official SST number as `ref`.
3. For a non-SST state, use the same category names, and take each answer from
   the state's own tax department rules.
4. Add `stripe` and `state_law` rows for what that state treats specially.
5. Cite the official source in every row. Each state's rules should be checked
   by a tax adviser before going live.
