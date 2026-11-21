export const identityDecisions = ["DIFFERENT_ENTITY", "SAME_ENTITY", "REVIEW"] as const;
export type IdentityDecision = typeof identityDecisions[number];
export type Prediction = { hit_id: string; alert_id: string; decision: IdentityDecision; reason_code: string; customer_record_id: string | null; reason: string; evidence: string[] };
export type IdentityTrace = { customer: { name: string; dob: number[] | null; countries: string[]; verified: boolean; records: string[] }; watchlist: { name: string; dobs: number[][]; countries: string[]; report: number[] | null }; path: string[]; gaps: string[] };
export type AlertReview = { alert_id: string; rationale: string; created_at: string };
export type ScreeningRun = { importId?: string; reviews?: AlertReview[]; storage?: "supabase" | "local"; source: string; synthetic: boolean; predictions: Prediction[]; traces: Record<string, IdentityTrace>; generatedAt?: string; durationSeconds?: number };
const codes: Record<IdentityDecision, string[]> = {
  DIFFERENT_ENTITY: ["TEMPORAL_IMPOSSIBILITY", "DOB_MISMATCH", "LOCATION_MISMATCH", "NAME_MISMATCH_VERIFIED", "ENTITY_TYPE_MISMATCH", "DECEASED"],
  SAME_ENTITY: ["NAME_DOB_LOCATION_MATCH", "NAME_DOB_MATCH", "NAME_LOCATION_MATCH"],
  REVIEW: ["INSUFFICIENT_DATA", "AMBIGUOUS_CUSTOMER_RECORD", "INSUFFICIENT_EVIDENCE"],
};
export function parsePredictions(text: string): Prediction[] {
  const seen = new Set<string>();
  const rows = text.split(/\r?\n/).filter(line => line.trim()).map((line, i) => {
    let row: Prediction;
    try { row = JSON.parse(line); } catch { throw new Error(`Line ${i + 1}: invalid JSON.`); }
    if (!row || typeof row !== "object" || !identityDecisions.includes(row.decision)
      || typeof row.hit_id !== "string" || !row.hit_id.trim() || typeof row.alert_id !== "string" || !row.alert_id.trim()
      || typeof row.reason !== "string" || !row.reason.trim() || !codes[row.decision].includes(row.reason_code)
      || !(row.customer_record_id === null || typeof row.customer_record_id === "string")
      || !Array.isArray(row.evidence) || !row.evidence.every(id => typeof id === "string")) throw new Error(`Line ${i + 1}: invalid prediction fields or reason code.`);
    if (seen.has(row.hit_id)) throw new Error(`Line ${i + 1}: duplicate hit ${row.hit_id}.`);
    seen.add(row.hit_id);
    return row;
  });
  if (!rows.length) throw new Error("The file contains no predictions.");
  return rows;
}
export function groupAlerts(rows: Prediction[]) {
  const groups = new Map<string, Prediction[]>();
  rows.forEach(row => groups.set(row.alert_id, [...(groups.get(row.alert_id) ?? []), row]));
  return [...groups].map(([id, hits]) => ({ id, hits, closed: hits.length > 0 && hits.every(h => h.decision === "DIFFERENT_ENTITY") }));
}
