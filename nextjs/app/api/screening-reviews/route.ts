import { cloudMode, config, serverClient } from "../../../lib/supabase";
import { hasAllDataAccess } from "../../../lib/access-scope";

export async function POST(request: Request) {
  const settings = cloudMode ? config() : null;
  if (!settings) return Response.json({ error: "Cloud review storage is unavailable." }, { status: 503 });
  const supabase = await serverClient(settings);
  const { data: auth } = await supabase.auth.getClaims();
  if (!auth?.claims.sub) return Response.json({ error: "Sign in again to close this review." }, { status: 401 });
  const { data: profile } = await supabase.from("analyst_profiles").select("review_role, data_scope, booking_entity").eq("user_id", auth.claims.sub).maybeSingle();
  if (!hasAllDataAccess(profile ?? undefined)) return Response.json({ error: "Senior access to this dataset is required." }, { status: 403 });
  const content = await request.json().catch(() => null);
  const rationale = typeof content?.rationale === "string" ? content.rationale.trim() : "";
  if (typeof content?.import_id !== "string" || !/^[a-f0-9]{64}$/.test(content.import_id) || typeof content?.alert_id !== "string" || !content.alert_id.trim() || !rationale || rationale.length > 1000) {
    return Response.json({ error: "Choose an alert and provide a closure rationale (up to 1,000 characters)." }, { status: 400 });
  }
  const { data, error } = await supabase.from("screening_alert_reviews").insert({ import_id: content.import_id, alert_id: content.alert_id, rationale })
    .select("alert_id, rationale, created_at").single();
  if (error) return Response.json({ error: error.code === "23505" ? "This review is already closed. Refresh to see its history." : "Could not close the review." }, { status: error.code === "23505" ? 409 : error.code === "42501" ? 403 : 502 });
  return Response.json(data, { status: 201 });
}
