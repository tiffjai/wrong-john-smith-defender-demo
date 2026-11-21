export const NOTE_MAX_LENGTH = 1000;
export const OFFLINE_NOTES_MESSAGE = "Offline demo: these synthetic notes are read-only. Sign in to add a note.";

const caseIdPattern = /^CASE-\d{2}$/;
const syntheticAuthors: Record<string, string> = {
  "SYN-ANALYST-UK": "Synthetic demo analyst",
  "SYN-REVIEWER-UK": "Synthetic demo reviewer",
};

export type CaseNoteInsert = { case_id: string; body: string };

export function prepareCaseNote(content: unknown): { ok: true; insert: CaseNoteInsert } | { ok: false; error: string } {
  const record = content !== null && typeof content === "object" ? content as Record<string, unknown> : {};
  const caseId = typeof record.case_id === "string" ? record.case_id : "";
  const body = typeof record.body === "string" ? record.body.trim() : "";
  if (!caseIdPattern.test(caseId)) return { ok: false, error: "Choose a screening case before adding a note." };
  if (!body || body.length > NOTE_MAX_LENGTH) return { ok: false, error: "Enter a note of 1 to 1,000 characters." };
  return { ok: true, insert: { case_id: caseId, body } };
}

export function caseNoteWriteError(code: string | undefined): { status: number; error: string } {
  if (code === "23514") return { status: 400, error: "Enter a note of 1 to 1,000 characters." };
  if (code === "23503") return { status: 400, error: "Choose a screening case before adding a note." };
  if (code === "42501") return { status: 403, error: "The note could not be saved for this booking entity." };
  return { status: 502, error: "The note could not be saved for this booking entity." };
}

export function caseNoteAuthor(authorId: string, viewerId?: string) {
  if (viewerId && authorId === viewerId) return "You";
  return syntheticAuthors[authorId] ?? authorId;
}

export function newestCaseNotes<T extends { case_id: string; created_at: string; id: string }>(notes: readonly T[], caseId: string) {
  return notes.filter((note) => note.case_id === caseId).sort((left, right) =>
    right.created_at.localeCompare(left.created_at) || right.id.localeCompare(left.id));
}
