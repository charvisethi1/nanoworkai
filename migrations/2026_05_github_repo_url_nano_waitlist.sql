-- Migration: add github_repo_url to nano_waitlist
-- Date: 2026-05-07
-- Note: the earlier 2026_04_github_repo_url.sql targeted 'linq_waitlist' (wrong table).
--       This migration correctly targets 'nano_waitlist'.

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'nano_waitlist'
          AND column_name = 'github_repo_url'
    ) THEN
        ALTER TABLE nano_waitlist ADD COLUMN github_repo_url text;
    END IF;
END
$$;
