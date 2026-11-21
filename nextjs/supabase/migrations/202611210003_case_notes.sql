begin;

create table if not exists public.case_notes (
  id uuid primary key default gen_random_uuid(),
  case_id text not null references public.screening_cases(id),
  author_id uuid not null default auth.uid() references auth.users(id),
  body text not null constraint case_notes_body_check check (char_length(trim(body)) between 1 and 1000),
  created_at timestamptz not null default now()
);

alter table public.case_notes drop constraint if exists case_notes_body_check;
alter table public.case_notes add constraint case_notes_body_check
  check (char_length(trim(body)) between 1 and 1000);

create index if not exists case_notes_case_created_idx on public.case_notes (case_id, created_at desc);

alter table public.case_notes enable row level security;

revoke all on public.case_notes from public, anon, authenticated;
grant select on public.case_notes to authenticated;
grant insert (case_id, body) on public.case_notes to authenticated;

drop policy if exists note_entity on public.case_notes;
create policy note_entity on public.case_notes for select to authenticated
  using (exists (select 1 from public.screening_cases c where c.id = case_notes.case_id));

drop policy if exists note_append on public.case_notes;
create policy note_append on public.case_notes for insert to authenticated
  with check ((select auth.uid()) = author_id and exists (
    select 1 from public.screening_cases c
    join public.analyst_profiles p on p.booking_entity = c.booking_entity
    where c.id = case_notes.case_id and p.user_id = (select auth.uid())
  ));

commit;
