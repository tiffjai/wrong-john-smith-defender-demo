"use client";

import { useState, type FormEvent } from "react";
import { caseNoteAuthor, newestCaseNotes, OFFLINE_NOTES_MESSAGE, prepareCaseNote } from "../lib/case-notes";
import type { CaseNote } from "../lib/types";

export function CaseNotes({ caseId, notes, canAnnotate, viewerId, onCreated }: {
  caseId: string; notes: CaseNote[]; canAnnotate: boolean; viewerId?: string;
  onCreated: (note: CaseNote) => void;
}) {
  const [body, setBody] = useState("");
  const [status, setStatus] = useState("");
  const [pending, setPending] = useState(false);
  const visible = newestCaseNotes(notes, caseId);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const prepared = prepareCaseNote({ case_id: caseId, body });
    if (!prepared.ok) { setStatus(prepared.error); return; }
    if (!canAnnotate) { setStatus(OFFLINE_NOTES_MESSAGE); return; }
    setPending(true);
    try {
      const response = await fetch("/api/notes", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(prepared.insert),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error ?? "Could not save this note.");
      onCreated(payload as CaseNote);
      setBody("");
      setStatus("Note saved.");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Could not save the note.");
    } finally {
      setPending(false);
    }
  }

  return <section className="case-notes" aria-label="Case notes">
    <h3>Case notes</h3>
    {canAnnotate ? <form onSubmit={submit}>
      <label>Note<textarea value={body} onChange={(event) => setBody(event.target.value)} rows={3} aria-describedby="note-length-hint"/></label>
      <p id="note-length-hint" className="muted">1 to 1,000 characters. The signed-in account is recorded as the author.</p>
      <button className="primary" disabled={pending || !body.trim()}>{pending ? "Saving…" : "Add note"}</button>
      {status && <span role="status" className="review-feedback">{status}</span>}
    </form> : <p className="muted">{OFFLINE_NOTES_MESSAGE}</p>}
    {visible.length === 0 && <p className="muted empty">No case notes yet.</p>}
    {visible.map((note) => {
      const author = caseNoteAuthor(note.author_id, viewerId);
      return <article key={note.id}><strong>{author}</strong>
        {author !== note.author_id && <code>{note.author_id}</code>}
        <time dateTime={note.created_at}>{new Date(note.created_at).toLocaleString()}</time><p>{note.body}</p></article>;
    })}
  </section>;
}
