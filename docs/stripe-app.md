# The Stripe App

The app is what a business installs from the Stripe Marketplace. It lives in
`stripe-app/` and has three parts:

- **`stripe-app.json`**, the manifest: the app's name, its icon, and the
  permissions it asks for. It asks to read events, read and write invoices, and
  read customers and products.
- **`src/views/AppSettings.tsx`**, the app's settings page in the business's
  Stripe Dashboard. The business ticks the states it collects sales tax in
  (Washington for now). The page saves that setting on our server, through
  `backend/settings_api.py`, signing each request so only that account can
  change its own settings.
- **`icon.png`**, the icon.

The tax itself is still calculated by the webhook on Vercel. The app only gives
it permission and settings.

## Accounts you need

Use two Stripe sandboxes:

- **Developer sandbox:** the one whose `sk_test_` key is already in Vercel as
  `STRIPE_SECRET_KEY`. You upload the app from here, and the Connect webhook
  lives here.
- **Business sandbox:** a second sandbox that plays a customer business. You
  install the app here. In the Dashboard, open the account menu and choose
  **Sandboxes > Create sandbox**.

## 1. Install the tools (once, on your computer)

1. **Node.js 22 or newer:** install the LTS version from nodejs.org. Check it
   with `node --version`.
2. **pnpm 10:** run `npm install -g pnpm@10`.
3. **Stripe CLI** (you may already have it from `stripe listen`). Check it with
   `stripe --version`. It needs version 1.52 or newer.
4. **The apps plugin:** run `stripe plugin install apps`.
5. Log in to the **developer sandbox**: run `stripe login` and pick that
   sandbox in the browser.

## 2. Upload the app

In PowerShell, in the repository folder:

    git pull
    cd stripe-app
    pnpm install
    stripe apps upload

The upload checks the manifest and sends it to Stripe. In the Dashboard of the
developer sandbox, the app then appears under **Apps > Created apps**
(Developers > Apps in some layouts).

To change something later, raise `"version"` in `stripe-app.json`
(0.1.0, then 0.1.1, and so on) and run `stripe apps upload` again.

## 3. Give the server the app's signing secret

1. In **Created apps**, open Tax Engine, click **⋯** and choose **Signing secret**.
2. Copy the secret (`absec_...`).
3. In Vercel, add it as `STRIPE_APP_SECRET`, then **Redeploy**.

Our server uses this secret to check that requests from the settings page
really come from Stripe.

## 4. Check the Connect webhook

In the developer sandbox, the **Connected accounts** webhook from
`docs/supabase.md` (step 3) must include these events: `apps.install.created`,
`apps.install.updated` and `apps.install.deleted`.

## 5. Install it in the business sandbox (external test)

1. In **Created apps**, open Tax Engine and choose **Set external test version**.
   Pick the version you uploaded.
2. On the app's **Details** tab, under **External testing**, set **Access** to
   **Anyone with the link**, then copy the install link.
3. Switch to the **business sandbox**, open the link, and install the app.

## 6. Check that it works

- **Supabase:** in **Table Editor > accounts**, a row appears for the business
  sandbox's `acct_...`, with `collect_in` set to `{WA}`.
- **Vercel Logs:** a line like `acct_...: app installed, collecting in WA` appears.
- **Settings page:** in the business sandbox, open **Settings > Apps > Tax Engine**.
  You'll see the Washington checkbox. Untick it, save, and the row in Supabase
  changes to `{}`.
- **Tax on invoices:** in the business sandbox, create a draft invoice for a
  customer with a Seattle address. Tax appears on it within a few seconds,
  exactly as in your own account.

If something fails, send me the line from Vercel's Logs or the error shown on
the settings page.
