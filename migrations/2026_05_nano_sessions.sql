-- nano_sessions: tracks conversation sessions separately from builds.
-- Allows "start fresh" detection and clarifying-question state without
-- touching the core nano_waitlist row.

create table if not exists public.nano_sessions (
  id              uuid primary key default gen_random_uuid(),
  phone_number    text not null,
  state           text not null default 'new'
    check (state in (
      'new', 'collecting_info', 'building',
      'awaiting_payment', 'complete', 'iterating'
    )),
  original_prompt text,
  clarifications  jsonb default '{}',
  build_id        uuid,
  project_id      uuid references public.projects(id) on delete set null,
  slug            text,
  started_at      timestamptz default now(),
  completed_at    timestamptz,
  paid_at         timestamptz
);

create index if not exists nano_sessions_phone_started_idx
  on public.nano_sessions (phone_number, started_at desc);

create index if not exists nano_sessions_state_idx
  on public.nano_sessions (state);

-- Extend nano_waitlist with session tracking
alter table public.nano_waitlist
  add column if not exists current_session_id uuid
    references public.nano_sessions(id) on delete set null,
  add column if not exists total_builds_count int not null default 0;

-- Add collecting_info to the state check constraint.
-- Drop the existing constraint (name may vary) and recreate it.
do $$
begin
  alter table public.nano_waitlist
    drop constraint if exists nano_waitlist_state_check;
exception when others then null;
end $$;

alter table public.nano_waitlist
  add constraint nano_waitlist_state_check check (state in (
    'awaiting_name',
    'awaiting_build',
    'collecting_info',
    'awaiting_description',
    'awaiting_contact',
    'awaiting_email',
    'awaiting_import_urls',
    'awaiting_payment',
    'awaiting_pricing_details',
    'awaiting_cmo',
    'awaiting_pages',
    'awaiting_expansion',
    'building',
    'complete',
    'questioning_1',
    'questioning_2',
    'questioning_3'
  ));
