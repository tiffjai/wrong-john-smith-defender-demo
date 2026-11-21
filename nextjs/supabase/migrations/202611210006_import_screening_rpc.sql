begin;
create function public.import_screening_run(p_id text, p_payload jsonb)
returns jsonb language plpgsql security definer set search_path = '' as $$
begin
  if not exists (select 1 from public.analyst_profiles p where p.user_id = (select auth.uid())
    and p.review_role = 'reviewer' and p.data_scope = 'all') then
    raise exception 'All-data Senior access required' using errcode = '42501';
  end if;
  if jsonb_typeof(p_payload->'predictions') is distinct from 'array'
    or jsonb_array_length(p_payload->'predictions') = 0 then
    raise exception 'Predictions required' using errcode = '22023';
  end if;
  insert into public.screening_imports(id,payload) values(p_id,p_payload) on conflict(id) do nothing;
  if exists (select 1 from public.screening_imports where id=p_id and payload <> p_payload) then
    raise exception 'Import identifier conflicts with stored content' using errcode = '22023';
  end if;
  insert into public.screening_import_alerts(import_id,alert_id,hits)
    select p_id,h.value->>'alert_id',jsonb_agg(h.value order by h.ordinality)
    from jsonb_array_elements(p_payload->'predictions') with ordinality h(value,ordinality)
    group by h.value->>'alert_id' on conflict(import_id,alert_id) do nothing;
  return jsonb_build_object('id',p_id,'hits',jsonb_array_length(p_payload->'predictions'),
    'alerts',(select count(*) from public.screening_import_alerts where import_id=p_id));
end;
$$;
revoke all on function public.import_screening_run(text,jsonb) from public, anon;
grant execute on function public.import_screening_run(text,jsonb) to authenticated;
commit;
