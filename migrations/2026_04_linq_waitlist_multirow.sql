-- =============================================================================
-- Migration: linq_waitlist multi-row support
-- Date:      2026-04-29
-- =============================================================================
-- Each completed build is now retained as its own row. A customer can have
-- many rows — one per build attempt. The most recent row (by created_at) is
-- always the "active" one.
--
-- Key changes:
--   1. build_id UUID — stable per-row identifier used for scoped writes so
--      UPDATE never accidentally touches a completed-build row.
--   2. created_at — ensures a deterministic ORDER BY for latest-row queries.
--   3. phone_number uniqueness dropped — multiple rows per phone are now valid.
--   4. Composite index on (phone_number, created_at DESC) — fast latest-row
--      lookup that underlies every get_waitlist_entry() call.
--
-- Existing single-row customers are unaffected: their row gets a build_id and
-- created_at backfilled, and the behaviour of all existing code paths is
-- identical until a second row is inserted.
--
-- Apply via Supabase SQL editor, `psql`, or `supabase db push`.
-- =============================================================================

-- 1. Stable per-row UUID used for scoped writes.
ALTER TABLE public.linq_waitlist
    ADD COLUMN IF NOT EXISTS build_id UUID NOT NULL DEFAULT gen_random_uuid();

-- 2. Row-creation timestamp used for "latest row" ordering.
--    Supabase adds this by default on new projects, but we ADD IF NOT EXISTS
--    to be safe on older schemas.
ALTER TABLE public.linq_waitlist
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now();

-- 3. Drop the unique constraint on phone_number so a customer can have
--    multiple rows (one per build).  The name may vary — try both the
--    Supabase-generated name and a common alternative.
ALTER TABLE public.linq_waitlist
    DROP CONSTRAINT IF EXISTS linq_waitlist_phone_number_key;

ALTER TABLE public.linq_waitlist
    DROP CONSTRAINT IF EXISTS linq_waitlist_pkey_phone;

-- 4. Fast lookup: latest row per customer.
CREATE INDEX IF NOT EXISTS linq_waitlist_phone_created_at_idx
    ON public.linq_waitlist (phone_number, created_at DESC);

-- 5. Fast lookup: row by build_id (used by all scoped UPDATE/SELECT calls).
CREATE UNIQUE INDEX IF NOT EXISTS linq_waitlist_build_id_idx
    ON public.linq_waitlist (build_id);
