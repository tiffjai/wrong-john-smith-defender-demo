begin;
create table public.screening_alert_reviews (
  import_id text not null,
  alert_id text not null,
  rationale text not null check (length(trim(rationale)) between 1 and 1000),
  reviewer_id uuid not null default auth.uid() references auth.users(id),
  created_at timestamptz not null default now(),
  primary key (import_id, alert_id),
  foreign key (import_id, alert_id) references public.screening_import_alerts(import_id, alert_id)
);
alter table public.screening_alert_reviews enable row level security;
revoke all on public.screening_alert_reviews from public, anon, authenticated;
grant select on public.screening_alert_reviews to authenticated;
grant insert (import_id, alert_id, rationale) on public.screening_alert_reviews to authenticated;
create policy senior_closure_read on public.screening_alert_reviews for select to authenticated
  using (exists (select 1 from public.screening_imports i where i.id = import_id));
create policy senior_closure_insert on public.screening_alert_reviews for insert to authenticated
  with check (reviewer_id = (select auth.uid()) and exists (
    select 1 from public.analyst_profiles p where p.user_id = (select auth.uid())
    and p.review_role = 'reviewer' and p.data_scope = 'all'
  ));
commit;
