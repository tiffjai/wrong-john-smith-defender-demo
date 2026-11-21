// @vitest-environment node
import { expect, test } from "vitest";
import { prepareScreeningImport } from "../lib/screening-import";

const hit = {hit_id:"H-1",alert_id:"A-1",decision:"REVIEW",reason_code:"INSUFFICIENT_DATA",customer_record_id:null,reason:"Missing birth date",evidence:["EV-1"]};
const run = {source:"O'Brien input",synthetic:false,predictions:[hit],traces:{}};

test("import preserves evidence, groups alerts and uses a stable content identity", () => {
  const first = prepareScreeningImport(run);
  const reordered = prepareScreeningImport({traces:{},predictions:[hit],synthetic:false,source:run.source});
  expect(first.id).toBe(reordered.id);
  expect(first.alerts).toBe(1);
  expect(first.hits).toBe(1);
  expect(first.sql).toContain("O''Brien input");
  expect(first.sql).toContain("EV-1");
  expect(first.sql).toContain("on conflict (id) do nothing");
  expect(first.sql).toContain("on conflict (import_id,alert_id) do nothing");
  expect(first.sql).not.toMatch(/delete from|drop table/i);
});

test("invalid or duplicate findings are rejected before creating an import", () => {
  for (const invalid of [{...run,predictions:[]},{...run,predictions:[hit,hit]},{...run,traces:null},{...run,predictions:[{...hit,reason_code:"invented"}]}]) {
    expect(() => prepareScreeningImport(invalid)).toThrow();
  }
});
