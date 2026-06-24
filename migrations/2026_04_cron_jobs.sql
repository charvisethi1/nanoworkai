-- =============================================================================
-- Migration: cron-driven preview lifecycle
-- Date:      2026-04-22
-- Branch:    cursor/add-cron-jobs-076d
-- =============================================================================
-- Adds the columns required by the two new Render cron jobs:
--
--   nanowork-preview-expiry  (hourly)
--     Enforces the 24h "preview comes down if unpaid" promise advertised in
--     PAYMENT_TEASER_MSG. Hits POST /internal/expire-previews, which queries
--     rows where preview_created_at is older than 24h, payment is not
--     confirmed, preview_expired_at IS NULL, and page_html is set. Then it
--     NULLs out page_html + page_slug (moved to expired_page_slug) and
--     stamps preview_expired_at.
--
--   nanowork-payment-nudge   (every 3h)
--     Gentle nudge at the 12–24h mark so we don't go silent until takedown.
--     Hits POST /internal/payment-nudge, which stamps payment_nudge_sent_at
--     on first nudge so we don't double-send.
--
-- Apply via Supabase SQL editor, `psql`, or `supabase db push`.
-- All new columns are nullable and default to NULL so existing rows are
-- unaffected and the cron queries safely skip them until the next preview
-- build re-populates preview_created_at.
-- =============================================================================

ALTER TABLE public.linq_waitlist
    ADD COLUMN IF NOT EXISTS preview_created_at    timestamptz,
    ADD COLUMN IF NOT EXISTS preview_expired_at    timestamptz,
    ADD COLUMN IF NOT EXISTS expired_page_slug     text,
    ADD COLUMN IF NOT EXISTS payment_nudge_sent_at timestamptz;

-- Indexes chosen to match the cron query shapes:
--   get_expired_previews  — state = 'awaiting_payment'
--                            AND preview_created_at < cutoff
--                            AND preview_expired_at IS NULL
--   get_previews_to_nudge — state = 'awaiting_payment'
--                            AND preview_created_at BETWEEN ... AND ...
--                            AND payment_nudge_sent_at IS NULL
-- A single partial index on (preview_created_at) filtered by the awaiting-
-- payment state covers both jobs without bloating the table.

CREATE INDEX IF NOT EXISTS linq_waitlist_preview_created_at_awaiting_idx
    ON public.linq_waitlist (preview_created_at)
    WHERE state = 'awaiting_payment'
      AND preview_created_at IS NOT NULL;
