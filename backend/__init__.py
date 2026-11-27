"""The multi-business backend: which Stripe accounts installed the app, and their settings.

    account_store.py   Account and the stores that keep them (in memory, or Supabase)
    event_router.py    sends each Stripe event to the right business, with its settings
"""
