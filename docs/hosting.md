# Hosting the Stripe webhook

Run `stripe_webhook.py` on a server so tax is added to Stripe invoices all the
time, without your computer or `stripe listen`. This guide uses
[Render](https://render.com), which can run it straight from this GitHub
repository using `render.yaml`. Any host that runs Python works the same way.

## 1. Create the service on Render

1. Sign up at render.com with your GitHub account. Allow it to see the Tax-Engine repository.
2. Choose **New > Blueprint** and pick the Tax-Engine repository. Render reads `render.yaml`.
3. It asks for two values:
   - `STRIPE_SECRET_KEY`: your `sk_test_...` key.
   - `STRIPE_WEBHOOK_SECRET`: type `whsec_later` for now. You get the real one in step 2.
4. Create it. When the deploy finishes, Render shows the address, for example
   `https://tax-engine-webhook.onrender.com`. Open it in a browser: it should say
   `tax engine webhook: ok`.

`render.yaml` uses the `starter` plan (about $7 a month), which is always on. The
free plan sleeps when idle, so the first event after a quiet spell can time out and
the tax arrives late, after Stripe retries. That is fine for trying it out: change
`plan: starter` to `plan: free`.

## 2. Tell Stripe where to send events

1. In the Stripe Dashboard, in the same sandbox or test mode as your key, go to
   **Developers > Webhooks > Add destination**.
2. Pick these events: `invoice.created`, `invoice.updated`, `invoiceitem.created`,
   `invoiceitem.deleted`.
3. Destination: webhook endpoint, URL `https://<your-render-address>/webhook`.
4. Create it, then reveal its **signing secret** (`whsec_...`).
5. In Render, open the service's **Environment** tab, set `STRIPE_WEBHOOK_SECRET` to
   that secret, and save. Render restarts the service.

## 3. Try it

Stop `stripe listen` and `python stripe_webhook.py` on your computer, then create or
edit a draft invoice for a Washington customer in the Dashboard. The tax appears
within a few seconds. Render's **Logs** tab shows a line per event, such as
`in_...: tax 6.39 (invoice.updated)`. Stripe's webhook page shows each delivery and
its response.

## Notes

- The webhook only accepts test keys (`sk_test_...`) for now, on purpose. Going live
  needs the checks in the README first.
- Washington rates come from DOR's address lookup service, and location names from
  `data/wa-dor/Rates_26Q4.csv`. Replace that file each quarter (the next one is due
  for January 1).
- For the monthly report, run `python tax_report.py 2026-11` on your computer. It
  reads the invoices from Stripe and needs nothing from the server.
