begin;

create table public.screening_imports (
  id text primary key check (id ~ '^[a-f0-9]{64}$'),
  payload jsonb not null check (
    jsonb_typeof(payload -> 'predictions') = 'array'
    and jsonb_typeof(payload -> 'traces') = 'object'
    and jsonb_typeof(payload -> 'source') = 'string'
    and jsonb_typeof(payload -> 'synthetic') = 'boolean'
    and payload ?& array['predictions', 'traces', 'source', 'synthetic']
  ),
  imported_at timestamptz not null default now()
);

create table public.screening_import_alerts (
  import_id text not null references public.screening_imports(id),
  alert_id text not null check (length(trim(alert_id)) > 0),
  hits jsonb not null check (jsonb_typeof(hits) = 'array' and jsonb_array_length(hits) > 0),
  primary key (import_id, alert_id)
);

alter table public.screening_imports enable row level security;
alter table public.screening_import_alerts enable row level security;
revoke all on public.screening_imports, public.screening_import_alerts from public, anon, authenticated;
grant select on public.screening_imports, public.screening_import_alerts to authenticated;

-- No booking-entity assignment exists in the source. Never infer one from a
-- person's country. Only explicitly all-data Seniors can read these imports.
create policy import_senior_read on public.screening_imports for select to authenticated
  using (exists (select 1 from public.analyst_profiles p
    where p.user_id = (select auth.uid()) and p.review_role = 'reviewer' and p.data_scope = 'all'));
create policy imported_alert_read on public.screening_import_alerts for select to authenticated
  using (exists (select 1 from public.screening_imports r where r.id = screening_import_alerts.import_id));

-- Imports are administrator-run transactions; dashboard users have no writes.
commit;
