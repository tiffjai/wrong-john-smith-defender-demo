import { cloudMode, config, serverClient } from "../../../lib/supabase";

export async function POST(request: Request) {
  const settings = cloudMode ? config() : null;
  if (!settings) return Response.json({ error: "Cloud review storage is unavailable." }, { status: 503 });
  const supabase = await serverClient(settings);
  const { data } = await supabase.auth.getClaims();
  if (!data?.claims.sub) return Response.json({ error: "Sign in again to save this review." }, { status: 401 });

  const content = await request.json().catch(() => null);
  const rationale = typeof content?.rationale === "string" ? content.rationale.trim() : "";
  if (typeof content?.case_id !== "string" || !/^CASE-\d{2}$/.test(content.case_id) ||
      !["awaiting_evidence", "escalated_sanctions", "escalated_legal", "resolved"].includes(content.decision) || !rationale || rationale.length > 1000) {
    return Response.json({ error: "Choose a decision and provide a rationale (up to 1,000 characters)." }, { status: 400 });
  }

  const { data: review, error } = await supabase.from("review_events")
    .insert({ case_id: content.case_id, decision: content.decision, rationale })
    .select("case_id, decision, rationale, created_at").single();
  if (error) return Response.json({ error: "The review could not be saved for this booking entity." }, { status: error.code === "42501" ? 403 : 502 });
  return Response.json(review, { status: 201 });
}
