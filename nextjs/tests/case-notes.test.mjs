import test from "node:test";
import assert from "node:assert/strict";
import { prepareCaseNote, newestCaseNotes, caseNoteWriteError } from "../lib/case-notes.ts";

test("note validation strips forged authors and validates case and length", () => {
  assert.deepEqual(prepareCaseNote({case_id: "CASE-08", body: "  Finding  ", author_id: "forged"}), {ok: true, insert: {case_id: "CASE-08", body: "Finding"}});
  for (const body of ["", "   ", "x".repeat(1001)]) assert.equal(prepareCaseNote({case_id: "CASE-08", body}).ok, false);
  assert.equal(prepareCaseNote({case_id: "CASE-08", body: "x".repeat(1000)}).ok, true);
  assert.equal(prepareCaseNote({case_id: "wrong", body: "Finding"}).ok, false);
});

test("note history is scoped, ordered and does not mutate input", () => {
  const notes = [{id: "a", case_id: "CASE-08", created_at: "2026-11-20"}, {id: "b", case_id: "CASE-08", created_at: "2026-11-21"}, {id: "c", case_id: "CASE-11", created_at: "2026-11-22"}];
  assert.deepEqual(newestCaseNotes(notes, "CASE-08").map(x => x.id), ["b", "a"]);
  assert.equal(notes[0].id, "a");
  assert.equal(caseNoteWriteError("42501").status, 403);
});
