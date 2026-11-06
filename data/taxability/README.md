# Product taxability, one file per state

Each file (`WA.csv`, ...) says which product categories are taxed in that
state. A product is tagged with one category; untagged products are `general`.

| Column | Meaning |
|---|---|
| `category` | the tag used on products, e.g. `groceries` |
| `taxable` | `yes` (full local rate), `no` (exempt), or for `shipping` also `proportional` |
| `description` | what the category covers, in plain words |
| `source` | the official page or law the rule comes from |

The `shipping` row says how delivery charges are taxed. `proportional` means
in the same share as the goods delivered, by price: a box with only groceries
ships tax-free, a box that is half clothing by price has half its shipping taxed.

These rules were researched from official sources in November 2026 and should
be checked by the client or a tax adviser before going live. States with no
file here tax `general` products and shipping in full; any other category raises an error so
nothing is taxed or exempted by guesswork.
