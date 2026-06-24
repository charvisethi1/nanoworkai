-- Migration: persist customer-scoped context.md + canonical app domain
--
-- Adds:
--   context_md             TEXT         - human-readable customer context artifact
--   context_md_updated_at  timestamptz  - last time context_md was refreshed
--   app_domain             TEXT         - canonical production URL for this build
--
-- These columns support tenant-isolated context injection and simple ops/debug
-- without parsing raw context_json blobs.

ALTER TABLE public.linq_waitlist
    ADD COLUMN IF NOT EXISTS context_md            TEXT,
    ADD COLUMN IF NOT EXISTS context_md_updated_at timestamptz,
    ADD COLUMN IF NOT EXISTS app_domain            TEXT;

CREATE INDEX IF NOT EXISTS idx_linq_waitlist_app_domain
    ON public.linq_waitlist (app_domain)
    WHERE app_domain IS NOT NULL;
