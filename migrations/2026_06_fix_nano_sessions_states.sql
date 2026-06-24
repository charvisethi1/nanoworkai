-- Fix nano_sessions CHECK constraint to include all states used by the code
-- Bug: 'collecting_pages_info' and 'awaiting_expansion' were missing from the constraint

ALTER TABLE public.nano_sessions
DROP CONSTRAINT nano_sessions_state_check;

ALTER TABLE public.nano_sessions
ADD CONSTRAINT nano_sessions_state_check CHECK (state IN (
  'new',
  'collecting_info',
  'collecting_pages_info',
  'building',
  'awaiting_payment',
  'awaiting_expansion',
  'complete',
  'iterating'
));
