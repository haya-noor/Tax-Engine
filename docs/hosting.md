# Hosting the Stripe webhook

Run `stripe_webhook.py` on a server so tax is added to Stripe invoices all the
time, without your computer or `stripe listen`. Two hosts are set
up: [Vercel](https://vercel.com) (free, no card) and [Render](https://render.com)
(the free plan asks for a card to verify you). Any host that runs Python works.

## Option A: Vercel (free, no card)

Vercel runs `api/webhook.py` on each request, so there is no server to keep
awake. `vercel.json` sends `/webhook` there.

1. Sign up at vercel.com with **Continue with GitHub** and pick the free **Hobby** plan.
2. **Add New > Project**, import the Tax-Engine repository. Framework preset: **Other**.
   Leave the build settings empty.
3. Open **Environment Variables** and add:
   - `STRIPE_SECRET_KEY`: your `sk_test_...` key
   - `STRIPE_WEBHOOK_SECRET`: `whsec_later` for now
   - `TAXENGINE_COLLECT_IN`: `WA`
4. Click **Deploy**. Vercel shows the address, for example `https://tax-engine-abc.vercel.app`.
   Open it in a browser: it should say `tax engine webhook: ok`.
5. Do step 2 below with the URL `https://<your-vercel-address>/webhook`.
6. Put the real signing secret in **Settings > Environment Variables** in Vercel, then
   **Deployments > ... > Redeploy**. Vercel only picks up a changed variable on a new deploy.

Vercel's Hobby plan is for personal, non-commercial use. Before you bill real
customers, move to a paid plan (Vercel Pro, or Render's always-on plan below).

If the address says `not configured`, a variable is missing or misspelled.
Vercel's **Logs** tab shows what the webhook printed for each event.

## Option B: Render

### 1. Create the service on Render

1. Sign up at render.com with your GitHub account. Allow it to see the Tax-Engine repository.
2. Choose **New > Blueprint** and pick the Tax-Engine repository. Render reads `render.yaml`.
3. It asks for two values:
   - `STRIPE_SECRET_KEY`: your `sk_test_...` key.
   - `STRIPE_WEBHOOK_SECRET`: type `whsec_later` for now. You get the real one in step 2.
4. Create it. When the deploy finishes, Render shows the address, for example
   `https://tax-engine-webhook.onrender.com`. Open it in a browser: it should say
   `tax engine webhook: ok`.

`render.yaml` uses Render's **free** plan. It sleeps after about 15 minutes with
no traffic, and takes up to a minute to wake. Stripe gives up on an event that
slow and tries again a few minutes later, so after a quiet spell the tax can
arrive late. Before you send an invoice, check the tax is on it; if it isn't,
open your Render address in a browser to wake the service, wait a minute, and
edit the invoice again (any small change). For real customers, switch to the
always-on plan: change `plan: free` to `plan: starter` (about $7 a month).

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
