-- =============================================================================
-- Migration: add github_repo_url column
-- Date:      2026-04-24
-- =============================================================================
-- Stores the GitHub repository URL created for each deployed application.
-- The release phase (Phase 5) writes this after pushing the generated code
-- to a dedicated GitHub repo so the founder can manage their codebase.
--
-- Safe to run multiple times — IF NOT EXISTS guards the ALTER.
-- =============================================================================

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'linq_waitlist'
          AND column_name = 'github_repo_url'
    ) THEN
        ALTER TABLE linq_waitlist ADD COLUMN github_repo_url text;
    END IF;
END
$$;
