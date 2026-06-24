-- Preview lifecycle status tracking for linq_waitlist rows.
-- Keeps onboarding `state` untouched while adding deployment-stage visibility.

alter table public.linq_waitlist
add column if not exists preview_status text;

alter table public.linq_waitlist
add column if not exists preview_status_updated_at timestamptz;

alter table public.linq_waitlist
add column if not exists preview_failure_reason text;

do $$
begin
  if not exists (
    select 1 from pg_constraint
    where conname = 'linq_waitlist_preview_status_chk'
  ) then
    alter table public.linq_waitlist
    add constraint linq_waitlist_preview_status_chk
    check (
      preview_status is null
      or preview_status in ('initiated', 'building', 'uploaded', 'deployed', 'failed')
    );
  end if;
end
$$;

create index if not exists idx_linq_waitlist_preview_status
  on public.linq_waitlist (preview_status)
  where preview_status is not null;
