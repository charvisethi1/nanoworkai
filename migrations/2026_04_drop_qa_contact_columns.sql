-- =============================================================================
-- Migration: drop Q&A and contact_preference columns
-- Date:      2026-04-22
-- Branch:    cursor/cleanup-waitlist-schema-3b1a
-- =============================================================================
-- The Q&A intake flow (questioning_1/2/3, awaiting_contact, awaiting_email)
-- has been removed from the codebase. The onboarding flow now goes directly
-- from awaiting_build → awaiting_payment, bypassing these steps entirely.
-- contact_preference is also removed: email is always collected when the
-- user provides one, without a separate contact-preference question.
--
-- These 7 columns are no longer read or written by any code path.
-- All existing rows can safely have these columns dropped.
--
-- Apply via Supabase SQL editor, `psql`, or `supabase db push`.
-- =============================================================================

ALTER TABLE public.linq_waitlist
    DROP COLUMN IF EXISTS q1_question,
    DROP COLUMN IF EXISTS q1_answer,
    DROP COLUMN IF EXISTS q2_question,
    DROP COLUMN IF EXISTS q2_answer,
    DROP COLUMN IF EXISTS q3_question,
    DROP COLUMN IF EXISTS q3_answer,
    DROP COLUMN IF EXISTS contact_preference;
