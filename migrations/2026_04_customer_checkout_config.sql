-- Migration: 2026_04_customer_checkout_config
--
-- Adds three columns to linq_waitlist that store the Stripe Checkout
-- configuration produced by provision_customer_infra:
--
--   customer_checkout_amount_cents  — product price in USD cents (e.g. 2900 = $29)
--   customer_checkout_interval      — "month", "year", or NULL for one-time
--
-- customer_checkout_url already exists from a prior deploy; the two new
-- columns are added here so the /checkout/{slug} endpoint can mint fresh
-- Checkout sessions without re-parsing the CFO conversation.

ALTER TABLE public.linq_waitlist
    ADD COLUMN IF NOT EXISTS customer_checkout_amount_cents INTEGER,
    ADD COLUMN IF NOT EXISTS customer_checkout_interval     TEXT;

-- Index speeds up the /checkout/{slug} lookup
CREATE INDEX IF NOT EXISTS idx_linq_waitlist_checkout_slug
    ON public.linq_waitlist (page_slug)
    WHERE customer_checkout_amount_cents IS NOT NULL;
