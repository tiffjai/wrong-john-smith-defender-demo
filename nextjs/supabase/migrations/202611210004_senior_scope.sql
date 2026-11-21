begin;

-- Existing accounts remain entity-scoped. Only an administrator can assign
-- all-data scope; authenticated clients still have no profile write grant.
alter table public.analyst_profiles
  add column if not exists data_scope text not null default 'entity';
alter table public.analyst_profiles
  add constraint analyst_profiles_data_scope_check
  check (data_scope in ('entity', 'all') and (data_scope <> 'all' or review_role = 'reviewer'));

alter policy case_entity on public.screening_cases to authenticated
  using (exists (
    select 1 from public.analyst_profiles p
    where p.user_id = (select auth.uid())
      and (p.booking_entity = screening_cases.booking_entity
        or (p.review_role = 'reviewer' and p.data_scope = 'all'))
  ));

alter policy review_append on public.review_events to authenticated
  with check ((select auth.uid()) = author_id and exists (
    select 1 from public.screening_cases c
    join public.analyst_profiles p on p.user_id = (select auth.uid())
    where c.id = review_events.case_id
      and (p.booking_entity = c.booking_entity or (p.review_role = 'reviewer' and p.data_scope = 'all'))
      and (review_events.decision <> 'resolved' or p.review_role = 'reviewer')
  ));

alter policy note_append on public.case_notes to authenticated
  with check ((select auth.uid()) = author_id and exists (
    select 1 from public.screening_cases c
    join public.analyst_profiles p on p.user_id = (select auth.uid())
    where c.id = case_notes.case_id
      and (p.booking_entity = c.booking_entity or (p.review_role = 'reviewer' and p.data_scope = 'all'))
  ));

alter policy review_entity on public.review_events to authenticated
  using (exists (select 1 from public.screening_cases c where c.id = review_events.case_id));
alter policy note_entity on public.case_notes to authenticated
  using (exists (select 1 from public.screening_cases c where c.id = case_notes.case_id));

-- Review/note SELECT policies inherit the screening case visibility.
-- No data changes, user creation, profile assignment or additional grants.
commit;
