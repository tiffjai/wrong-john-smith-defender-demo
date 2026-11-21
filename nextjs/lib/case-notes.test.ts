import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import caseIndex from "../data/case-index.json";
import demoNotes from "../data/case-notes.json";
import { caseNoteAuthor, caseNoteWriteError, newestCaseNotes, NOTE_MAX_LENGTH, prepareCaseNote } from "./case-notes";

const migrationPath = new URL("../supabase/migrations/202611210002_case_notes.sql", import.meta.url);
const reviewMigrationPath = new URL("../supabase/migrations/202611210001_defender_demo.sql", import.meta.url);

test("accepts a trimmed note and drops any client author", () => {
  const prepared = prepareCaseNote({
    case_id: "CASE-08",
    body: "  Synthetic note for the analyst.  ",
    author_id: "00000000-0000-0000-0000-000000000099",
    author: "Eve",
    created_at: "2000-01-01T00:00:00.000Z",
    id: "forged",
  });
  assert.deepEqual(prepared, { ok: true, insert: { case_id: "CASE-08", body: "Synthetic note for the analyst." } });
  assert.deepEqual(Object.keys(prepared.ok ? prepared.insert : {}), ["case_id", "body"]);
});

test("rejects an empty, blank, or over-long note", () => {
  assert.equal(prepareCaseNote({ case_id: "CASE-01", body: "" }).ok, false);
  assert.equal(prepareCaseNote({ case_id: "CASE-01", body: "   " }).ok, false);
  assert.equal(prepareCaseNote({ case_id: "CASE-01", body: 12 }).ok, false);
  const limit = prepareCaseNote({ case_id: "CASE-01", body: "a".repeat(NOTE_MAX_LENGTH) });
  const over = prepareCaseNote({ case_id: "CASE-01", body: "a".repeat(NOTE_MAX_LENGTH + 1) });
  assert.equal(limit.ok, true);
  assert.equal(over.ok, false);
  if (!over.ok) assert.equal(over.error, "Enter a note of 1 to 1,000 characters.");
});

test("rejects a missing case before accepting the body", () => {
  const prepared = prepareCaseNote({ body: "A note without a case.", author_id: "spoofed" });
  assert.deepEqual(prepared, { ok: false, error: "Choose a screening case before adding a note." });
  assert.equal(prepareCaseNote({ case_id: "CASE-1", body: "Too short an id." }).ok, false);
  assert.equal(prepareCaseNote(null).ok, false);
});

test("maps database failures without echoing the database message", () => {
  assert.deepEqual(caseNoteWriteError("23514"), { status: 400, error: "Enter a note of 1 to 1,000 characters." });
  assert.deepEqual(caseNoteWriteError("23503"), { status: 400, error: "Choose a screening case before adding a note." });
  assert.equal(caseNoteWriteError("42501").status, 403);
  assert.equal(caseNoteWriteError("XX000").status, 502);
  assert.equal(caseNoteWriteError(undefined).error.includes("password"), false);
});

test("labels the signed-in author and keeps other authors visible", () => {
  const viewer = "11111111-1111-1111-1111-111111111111";
  assert.equal(caseNoteAuthor(viewer, viewer), "You");
  assert.equal(caseNoteAuthor("22222222-2222-2222-2222-222222222222", viewer), "22222222-2222-2222-2222-222222222222");
  assert.equal(caseNoteAuthor("SYN-ANALYST-UK", viewer), "Synthetic demo analyst");
  assert.equal(caseNoteAuthor("SYN-REVIEWER-UK"), "Synthetic demo reviewer");
});

test("shows newest notes for one case without rewriting the source list", () => {
  const notes = [
    { id: "older", case_id: "CASE-11", created_at: "2026-11-20T11:00:00.000Z" },
    { id: "other", case_id: "CASE-08", created_at: "2026-11-21T12:00:00.000Z" },
    { id: "newer", case_id: "CASE-11", created_at: "2026-11-21T09:30:00.000Z" },
  ];
  assert.deepEqual(newestCaseNotes(notes, "CASE-11").map((note) => note.id), ["newer", "older"]);
  assert.deepEqual(notes.map((note) => note.id), ["older", "other", "newer"]);
});

test("synthetic demo notes belong to known cases and pass the length check", () => {
  const ids = new Set(caseIndex.map((entry) => entry.id));
  assert.ok(demoNotes.length > 0);
  for (const note of demoNotes) {
    assert.equal(note.id.startsWith("SYN-"), true);
    assert.equal(ids.has(note.case_id), true);
    assert.equal(prepareCaseNote(note).ok, true);
    assert.match(note.body, /Synthetic rehearsal/);
  }
});

test("case notes are append-only on the screening case and ignore client authors", () => {
  const sql = readFileSync(migrationPath, "utf8");
  assert.match(sql, /references public\.screening_cases\(id\)/);
  assert.match(sql, /author_id uuid not null default auth\.uid\(\)/);
  assert.match(sql, /char_length\(trim\(body\)\) between 1 and 1000/);
  assert.match(sql, /enable row level security/);
  assert.match(sql, /revoke all on public\.case_notes from public, anon, authenticated/);
  assert.match(sql, /grant insert \(case_id, body\) on public\.case_notes to authenticated/);
  assert.doesNotMatch(sql, /grant insert \(case_id, body, author_id\)/);
  assert.match(sql, /auth\.uid\(\)\) = author_id/);
  assert.match(sql, /for select to authenticated/);
  assert.match(sql, /for insert to authenticated/);
  assert.doesNotMatch(sql, /for update/i);
  assert.doesNotMatch(sql, /for delete/i);
  assert.doesNotMatch(sql, /grant update/i);
  assert.doesNotMatch(sql, /grant delete/i);
  assert.doesNotMatch(sql, /review_events/);
  assert.doesNotMatch(sql, /drop table/i);
  assert.doesNotMatch(sql, /delete from/i);
});

test("the note route attributes the author from the session insert default", () => {
  const source = readFileSync(new URL("../app/api/notes/route.ts", import.meta.url), "utf8");
  assert.match(source, /prepareCaseNote\(content\)/);
  assert.match(source, /\.insert\(prepared\.insert\)/);
  assert.match(source, /getClaims\(\)/);
  assert.doesNotMatch(source, /author_id:\s*content/);
  assert.doesNotMatch(source, /author_id:\s*.*claims/);
  assert.doesNotMatch(source, /content\.author/);
});

test("existing review history stays append-only", () => {
  const sql = readFileSync(reviewMigrationPath, "utf8");
  assert.match(sql, /grant insert \(case_id, decision, rationale\) on public\.review_events to authenticated/);
  assert.match(sql, /author_id uuid not null default auth\.uid\(\)/);
  assert.match(sql, /create policy review_append/);
  assert.doesNotMatch(sql, /for update/i);
  assert.doesNotMatch(sql, /for delete/i);
  assert.doesNotMatch(sql, /case_notes/);
});
