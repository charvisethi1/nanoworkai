-- Add feedback_loop to nano_waitlist state check constraint
-- This state is used for the post-payment iterative refinement loop.

do $$ begin
  alter table public.nano_waitlist
    drop constraint if exists nano_waitlist_state_check;
exception when others then null;
end $$;

alter table public.nano_waitlist
  add constraint nano_waitlist_state_check check (state in (
    'awaiting_name',
    'awaiting_build',
    'collecting_info',
    'collecting_pages_info',
    'awaiting_description',
    'awaiting_contact',
    'awaiting_email',
    'awaiting_import_urls',
    'awaiting_payment',
    'awaiting_pricing_details',
    'awaiting_cmo',
    'awaiting_pages',
    'awaiting_expansion',
    'feedback_loop',
    'building',
    'complete',
    'questioning_1',
    'questioning_2',
    'questioning_3'
  ));
