# Many businesses: the Supabase backend

When the app is on the Stripe Marketplace, many businesses install it. The
webhook has to know which businesses installed it and what each one's settings
are. That list lives in a Supabase database: one row per business, in the
`accounts` table.

## How it works

1. A business installs the app. Stripe sends `apps.install.created` to our
   Connect webhook endpoint, with `account` set to the business's Stripe account
   (`acct_...`). The webhook adds a row for that account, collecting in `WA`.
2. That business creates a draft invoice. Stripe sends `invoice.created` with
   the same `account`. The webhook looks the account up. If the app is installed,
   it taxes the invoice using our Stripe key acting for that account (Stripe's
   `Stripe-Account` header) and the account's own settings.
3. The business uninstalls the app. Stripe sends `apps.install.deleted`, the
   row is marked `uninstalled`, and the webhook stops taxing that business's
   invoices. A later reinstall keeps the old settings.

Events without `account` come from our own Stripe account. They are taxed as
before, so the current setup keeps working with or without Supabase.

The code is in `backend/`:
- `account_store.py` reads and writes the table.
- `event_router.py` sends each event to the right business.

The table itself is defined in `supabase/migrations/001_accounts.sql`.

Live mode is refused for now: events with `livemode: true` are not taxed until
going live is enabled on purpose.

## Setup (once)

### 1. Create the Supabase project

1. At supabase.com, choose **New project**. The free plan is enough. Name it
   `taxengine`, set a database password and pick a region near the US West Coast.
2. When it's ready, open **SQL Editor > New query**, paste the whole contents of
   `supabase/migrations/001_accounts.sql`, and click **Run**. Then open
   **Table Editor** and check that the `accounts` table is there.
3. Open **Project Settings > API** (or **Data API**) and copy:
   - the **Project URL**, `https://xxxx.supabase.co`
   - the **secret key** (`sb_secret_...`, under **Secret keys**). Older projects
     call it the **service_role** key; either works.

   Keep the service role key secret. It can read and write everything, so it
   only ever goes into Vercel's environment variables, never into the app's UI
   or into git.

### 2. Give the keys to Vercel

In Vercel, open the project, go to **Settings > Environment Variables** and add:
- `SUPABASE_URL`: the Project URL
- `SUPABASE_SERVICE_ROLE_KEY`: the service role key

Then go to **Deployments > ... > Redeploy**.

### 3. Add the Connect webhook endpoint in Stripe

Events from businesses that installed the app arrive on a separate *Connect*
endpoint, which has its own signing secret.

1. In the Stripe Dashboard (test mode), go to **Developers > Webhooks > Add destination**.
2. Choose **Connected and v2 accounts** (also shown as "Listen to events on
   Connected accounts").
3. Pick these events: `invoice.created`, `invoice.updated`, `invoiceitem.created`,
   `invoiceitem.deleted`, `apps.install.created`, `apps.install.updated` and
   `apps.install.deleted`. On API versions before 2026-09-30, the install events
   are called `app.install.*` instead.
4. Set the URL to the same address as before: `https://tax-engine-titu.vercel.app/webhook`.
5. Copy its signing secret (`whsec_...`). In Vercel, add it as
   `STRIPE_CONNECT_WEBHOOK_SECRET`, then redeploy.

The webhook accepts events signed with either secret: `STRIPE_WEBHOOK_SECRET`
for our own account, and `STRIPE_CONNECT_WEBHOOK_SECRET` for businesses.

## Checking it

Vercel's **Logs** show one line per event:
- `acct_...: app installed, collecting in WA`
- `acct_...: in_...: tax 8.44 (invoice.created)`
- `acct_...: invoice.created ignored: the app is not installed`

To see every install, open the `accounts` table in Supabase's Table Editor.

Install events only start arriving once the Stripe App itself exists and a test
account installs it. That's the next step: the app manifest (`stripe-app.json`)
and its upload to Stripe.
