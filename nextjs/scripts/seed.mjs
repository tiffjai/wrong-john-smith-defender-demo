import { readFileSync } from "node:fs";

const cases = JSON.parse(readFileSync(new URL("../data/case-index.json", import.meta.url), "utf8"));
const literal = (value) => `'${value.replaceAll("'", "''")}'`;
console.log("begin;");
for (const { id, title, booking_entity, snapshot } of cases) {
  const packet = JSON.parse(readFileSync(new URL(`../data/evidence_packet_${id}.json`, import.meta.url), "utf8"));
  if (packet.synthetic !== true || packet.case_id !== id) throw new Error(`Invalid fixture for ${id}`);
  const recommendation = id === "CASE-11"
    ? `${literal(readFileSync(new URL("../data/recommendation_CASE-11.json", import.meta.url), "utf8"))}::jsonb`
    : "null";
  console.log(`insert into public.screening_cases (id, title, booking_entity, snapshot, packet, recommendation)
values (${[id, title, booking_entity, snapshot].map(literal).join(", ")}, ${literal(JSON.stringify(packet))}::jsonb, ${recommendation})
on conflict (id) do nothing;`);
  if (id === "CASE-08" && packet.sanctions_list) {
    console.log(`update public.screening_cases
set packet = jsonb_set(packet, '{sanctions_list}', ${literal(JSON.stringify(packet.sanctions_list))}::jsonb)
where id = 'CASE-08' and booking_entity = 'UK' and packet -> 'synthetic' = 'true'::jsonb
  and not (packet ? 'sanctions_list') and packet @> '{"records":[{"record_id":"SYN-08-C"}]}'::jsonb;`);
  }
}
console.log("commit;");
