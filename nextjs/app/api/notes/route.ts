import { caseNoteWriteError, prepareCaseNote } from "../../../lib/case-notes";
import { cloudMode, config, serverClient } from "../../../lib/supabase";

export async function POST(request: Request) {
  const settings = cloudMode ? config() : null;
  if (!settings) return Response.json({ error: "Cloud note storage is unavailable." }, { status: 503 });
  const supabase = await serverClient(settings);
  const { data } = await supabase.auth.getClaims();
  if (!data?.claims.sub) return Response.json({ error: "Sign in again to save this note." }, { status: 401 });

  const content = await request.json().catch(() => null);
  const prepared = prepareCaseNote(content);
  if (!prepared.ok) return Response.json({ error: prepared.error }, { status: 400 });

  const { data: note, error } = await supabase.from("case_notes")
    .insert(prepared.insert)
    .select("id, case_id, author_id, body, created_at").single();
  if (error) {
    const failure = caseNoteWriteError(error.code);
    return Response.json({ error: failure.error }, { status: failure.status });
  }
  return Response.json(note, { status: 201 });
}
