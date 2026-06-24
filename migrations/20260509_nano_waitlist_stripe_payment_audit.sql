-- Stripe checkout reconciliation + audit on nano_waitlist (payment success URL + webhooks).
alter table public.nano_waitlist
  add column if not exists stripe_checkout_session_id text,
  add column if not exists stripe_payment_intent_id text,
  add column if not exists paid_at timestamptz;

create index if not exists nano_waitlist_stripe_checkout_session_id_idx
  on public.nano_waitlist (stripe_checkout_session_id)
  where stripe_checkout_session_id is not null;
