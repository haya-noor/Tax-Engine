-- Businesses that installed the tax engine app, one row per Stripe account.
-- Run once in Supabase: SQL Editor > New query > paste > Run.

create table if not exists public.accounts (
    account_id   text primary key,                    -- the business's Stripe account, acct_...
    status       text not null default 'active'       -- active or uninstalled
                 check (status in ('active', 'uninstalled')),
    livemode     boolean not null default false,      -- false: installed in a sandbox / test mode
    install_id   text,                                -- Stripe's App Install id
    collect_in   text[] not null default '{WA}',      -- states the business collects tax in
    installed_at timestamptz not null default now(),
    updated_at   timestamptz not null default now()
);

create or replace function public.touch_updated_at() returns trigger
language plpgsql as $$
begin
    new.updated_at = now();
    return new;
end $$;

drop trigger if exists accounts_touch on public.accounts;
create trigger accounts_touch before update on public.accounts
    for each row execute function public.touch_updated_at();

-- Only the server (service role key) may read or write; the public anon key gets nothing.
-- The grant is explicit so it works even when "Grant API access to new tables
-- automatically" was left off when the project was created.
alter table public.accounts enable row level security;
revoke all on public.accounts from anon, authenticated;
grant select, insert, update on public.accounts to service_role;
