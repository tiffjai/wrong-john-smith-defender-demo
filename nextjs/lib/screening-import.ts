import { createHash } from "node:crypto";
import { parsePredictions, type ScreeningRun } from "./entity-resolution";

export function prepareScreeningImport(input: unknown) {
  const run = input as ScreeningRun;
  if (!run || typeof run.source !== "string" || !run.source.trim() || typeof run.synthetic !== "boolean"
    || !Array.isArray(run.predictions) || !run.traces || typeof run.traces !== "object" || Array.isArray(run.traces)) throw new Error("Invalid screening run.");
  parsePredictions(run.predictions.map(hit => JSON.stringify(hit)).join("\n"));
  const canonical = (value: unknown): unknown => Array.isArray(value) ? value.map(canonical)
    : value && typeof value === "object" ? Object.fromEntries(Object.entries(value).sort(([a], [b]) => a.localeCompare(b)).map(([key, item]) => [key, canonical(item)])) : value;
  const payload = JSON.stringify(canonical(run));
  const id = createHash("sha256").update(payload).digest("hex");
  const literal = `'${payload.replaceAll("'", "''")}'::jsonb`;
  const sql = `begin;
insert into public.screening_imports (id,payload) values ('${id}',${literal}) on conflict (id) do nothing;
insert into public.screening_import_alerts (import_id,alert_id,hits)
select r.id, h.value->>'alert_id', jsonb_agg(h.value order by h.ordinality)
from public.screening_imports r cross join lateral jsonb_array_elements(r.payload->'predictions') with ordinality h(value,ordinality)
where r.id='${id}' group by r.id,h.value->>'alert_id' on conflict (import_id,alert_id) do nothing;
commit;
select id, jsonb_array_length(payload->'predictions') as hits,
(select count(*) from public.screening_import_alerts a where a.import_id=r.id) as alerts
from public.screening_imports r where id='${id}';`;
  return { id, sql, hits: run.predictions.length, alerts: new Set(run.predictions.map(hit => hit.alert_id)).size };
}
