begin;

create table if not exists public.analyst_profiles (
  user_id uuid primary key references auth.users(id) on delete cascade,
  booking_entity text not null check (booking_entity in ('UK', 'US')),
  review_role text not null check (review_role in ('analyst', 'reviewer'))
);

create table if not exists public.screening_cases (
  id text primary key check (id ~ '^CASE-[0-9]{2}$'),
  title text not null,
  booking_entity text not null check (booking_entity in ('UK', 'US')),
  snapshot text not null check (snapshot in ('V1', 'V2')),
  recommendation jsonb check (recommendation is null or (recommendation ->> 'case_id') is not distinct from id),
  packet jsonb not null check (
    (packet -> 'synthetic') is not distinct from 'true'::jsonb
    and (packet ->> 'case_id') is not distinct from id
  )
);

create table if not exists public.review_events (
  id uuid primary key default gen_random_uuid(),
  case_id text not null references public.screening_cases(id),
  author_id uuid not null default auth.uid() references auth.users(id),
  decision text not null check (decision in ('awaiting_evidence', 'escalated_sanctions', 'escalated_legal', 'resolved')),
  rationale text not null check (char_length(trim(rationale)) between 1 and 1000),
  created_at timestamptz not null default now()
);

alter table public.analyst_profiles enable row level security;
alter table public.screening_cases enable row level security;
alter table public.review_events enable row level security;

revoke all on public.analyst_profiles, public.screening_cases, public.review_events from public, anon, authenticated;
grant select on public.analyst_profiles, public.screening_cases, public.review_events to authenticated;
grant insert (case_id, decision, rationale) on public.review_events to authenticated;

create policy profile_self on public.analyst_profiles for select to authenticated
  using (user_id = (select auth.uid()));

create policy case_entity on public.screening_cases for select to authenticated
  using (exists (
    select 1 from public.analyst_profiles p
    where p.user_id = (select auth.uid()) and p.booking_entity = screening_cases.booking_entity
  ));

create policy review_entity on public.review_events for select to authenticated
  using (exists (select 1 from public.screening_cases c where c.id = review_events.case_id));

create policy review_append on public.review_events for insert to authenticated
  with check ((select auth.uid()) = author_id and exists (
    select 1 from public.screening_cases c
    join public.analyst_profiles p on p.booking_entity = c.booking_entity
    where c.id = review_events.case_id and p.user_id = (select auth.uid())
      and (review_events.decision <> 'resolved' or p.review_role = 'reviewer')
  ));

commit;
