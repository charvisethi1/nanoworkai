-- =============================================================================
-- Migration: page build type taxonomy column (linq_waitlist + pitch_pages)
-- Date:      2026-05-02
-- =============================================================================
-- Stores the closed taxonomy used for HTML generation routing: landing, tool,
-- form, directory, portfolio, booking, app, info, other.
-- Existing rows default to ``landing`` so post-payment flows keep working.
-- Apply via Supabase SQL editor, ``psql``, or ``supabase db push``.
-- =============================================================================

ALTER TABLE public.linq_waitlist
    ADD COLUMN IF NOT EXISTS build_type TEXT NOT NULL DEFAULT 'landing';

ALTER TABLE public.pitch_pages
    ADD COLUMN IF NOT EXISTS build_type TEXT NOT NULL DEFAULT 'landing';

UPDATE public.linq_waitlist
SET build_type = 'landing'
WHERE build_type IS NULL;

UPDATE public.pitch_pages
SET build_type = 'landing'
WHERE build_type IS NULL;
