# Washington DOR files (optional)

Put Washington Department of Revenue rate files here, unzipped, to look up rates
by ZIP+4 without the network:

- the rates file from Rates_YYQn.zip: location codes, names and rates. Gives
  readable names such as "Bellevue (1704)".
- the ZIP+4 short file from Zip4QnYYC.zip: ZIP+4 ranges to location codes.

Download them each quarter from
https://dor.wa.gov/taxes-rates/sales-use-tax-rates/downloadable-database

Without these files, Washington rates still come by street address from DOR's
lookup service when it is turned on. See `taxengine/wa_dor.py`.
