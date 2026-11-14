# Hosting the Stripe webhook

Run the webhook on a server so tax is added to Stripe invoices all the time,
without your computer or `stripe listen`. This guide uses
[Vercel](https://vercel.com): its free Hobby plan needs no card, and it runs
`api/webhook.py` on each request, so there is no server to keep awake.
`vercel.json` sends `/webhook` there. Any host that runs Python also works
(`python stripe_webhook.py` with `HOST=0.0.0.0` and `PORT` set).

## 1. Deploy on Vercel

1. Sign up at vercel.com with **Continue with GitHub** and pick the free **Hobby** plan.
2. **Add New > Project**, import the Tax-Engine repository. Framework preset: **Other**.
   Leave the build settings empty.
3. Open **Environment Variables** and add:
   - `STRIPE_SECRET_KEY`: your `sk_test_...` key
   - `STRIPE_WEBHOOK_SECRET`: `whsec_later` for now; you get the real one in step 2
   - `TAXENGINE_COLLECT_IN`: `WA`
4. Click **Deploy**. Vercel shows the address, for example `https://tax-engine-abc.vercel.app`.
   Open it in a browser: it should say `tax engine webhook: ok`. If it says
   `not configured`, a variable is missing or misspelled.

## 2. Tell Stripe where to send events

1. In the Stripe Dashboard, in the same sandbox or test mode as your key, go to
   **Developers > Webhooks > Add destination**.
2. Pick these events: `invoice.created`, `invoice.updated`, `invoiceitem.created`,
   `invoiceitem.deleted`.
3. Destination: webhook endpoint, URL `https://<your-vercel-address>/webhook`.
4. Create it, then reveal its **signing secret** (`whsec_...`).
5. In Vercel, go to **Settings > Environment Variables**, set `STRIPE_WEBHOOK_SECRET`
   to that secret, then **Deployments > ... > Redeploy**. Vercel only picks up a
   changed variable on a new deploy.

## 3. Try it

Stop `stripe listen` and `python stripe_webhook.py` on your computer, then create or
edit a draft invoice for a Washington customer in the Dashboard. The tax appears
within a few seconds. Vercel's **Logs** tab shows a line per event, such as
`in_...: tax 6.39 (invoice.updated)`. Stripe's webhook page shows each delivery and
its response.

## Notes

- Vercel's Hobby plan is for personal, non-commercial use. Before billing real
  customers, move to a paid plan.
- The webhook only accepts test keys (`sk_test_...`) for now, on purpose. Going live
  needs the checks in the README first.
- Washington rates come from DOR's address lookup service, and location names from
  `data/wa-dor/Rates_26Q4.csv`. Replace that file each quarter (the next one is due
  for January 1).
- For the monthly report, run `python tax_report.py 2026-11` on your computer. It
  reads the invoices from Stripe and needs nothing from the server.
