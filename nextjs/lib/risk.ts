import { groupAlerts, type AlertReview, type IdentityTrace, type Prediction, type ScreeningRun } from "./entity-resolution";
import type { Case, Review } from "./types";
import { reviewStage } from "./review-queue";

export const riskModelVersion = "screening-triage-v1";
export const riskBands = ["High", "Medium", "Low"] as const;
export type RiskBand = typeof riskBands[number];
export type RiskDriver = { label: string; points: number; detail: string };
export type RiskAssessment = { score: number; band: RiskBand; drivers: RiskDriver[]; nextAction: string };
export type RiskItem = RiskAssessment & { id: string; title: string; status: "Open" | "Clear" | "Closed"; hits: number; unresolved: number; same: number; gaps: number; traceCoverage: number; evidence: number; findings: string[] };
export function riskBand(score: number): RiskBand { return score >= 70 ? "High" : score >= 35 ? "Medium" : "Low"; }
export function indexTraces(traces: ScreeningRun["traces"]) {
  const index = new Map<string, IdentityTrace[]>();
  Object.entries(traces).forEach(([key, trace]) => {
    const hit = key.split(":")[0];
    index.set(hit, [...(index.get(hit) ?? []), trace]);
  });
  return index;
}
export function assessHit(hit: Prediction, traces: IdentityTrace[] = []): RiskAssessment {
  const base = hit.decision === "SAME_ENTITY" ? 75 : hit.decision === "REVIEW" ? 40 : 10;
  const drivers: RiskDriver[] = [{ label: hit.decision === "SAME_ENTITY" ? "Identity agreement" : hit.decision === "REVIEW" ? "Unresolved identity" : "Identity exclusion", points: base, detail: hit.reason }];
  // Exclusion evidence stays low priority. Gaps affect unresolved or matching hits only.
  if (hit.decision !== "DIFFERENT_ENTITY") {
    if (hit.customer_record_id === "AMBIGUOUS" || hit.customer_record_id === null || traces.length > 1) drivers.push({ label: "Customer ambiguity", points: 15, detail: "A unique customer identity has not been established." });
    const gaps = new Set(traces.flatMap(trace => trace.gaps));
    if (gaps.size) drivers.push({ label: "Evidence gaps", points: Math.min(15, gaps.size * 5), detail: [...gaps].join("; ") });
    if (!traces.length) drivers.push({ label: "Source trace unavailable", points: 10, detail: "Record-level comparison is unavailable in this run." });
    else if (traces.some(trace => !trace.customer.verified)) drivers.push({ label: "Identity verification gap", points: 10, detail: "At least one customer identity uses declared rather than approved evidence." });
    if (!hit.evidence.length) drivers.push({ label: "Evidence IDs unavailable", points: 10, detail: "No supporting evidence IDs were supplied." });
  }
  const score = Math.min(100, drivers.reduce((total, driver) => total + driver.points, 0));
  return { score, band: riskBand(score), drivers, nextAction: hit.decision === "SAME_ENTITY" ? "Review the identity agreement and determine whether specialist escalation is required." : hit.decision === "REVIEW" ? "Resolve customer ambiguity and obtain the missing identity evidence." : "Validate the exclusion evidence before recording the review outcome." };
}
export function assessAlerts(run: ScreeningRun, reviews: AlertReview[] = run.reviews ?? []): RiskItem[] {
  const traces = indexTraces(run.traces);
  const closed = new Set(reviews.map(review => review.alert_id));
  return groupAlerts(run.predictions).map(alert => {
    const assessed = alert.hits.map(hit => ({ hit, risk: assessHit(hit, traces.get(hit.hit_id)) }));
    const highest = assessed.reduce((a, b) => b.risk.score > a.risk.score ? b : a);
    const names = [...new Set(alert.hits.flatMap(hit => traces.get(hit.hit_id) ?? []).map(trace => trace.customer.name))];
    return { ...highest.risk, id: alert.id, title: names.join(" / ") || alert.hits[0].customer_record_id || "Unresolved customer", status: closed.has(alert.id) ? "Closed" : alert.closed ? "Clear" : "Open", hits: alert.hits.length,
      unresolved: alert.hits.filter(hit => hit.decision === "REVIEW").length, same: alert.hits.filter(hit => hit.decision === "SAME_ENTITY").length,
      gaps: new Set(alert.hits.flatMap(hit => (traces.get(hit.hit_id) ?? []).flatMap(trace => trace.gaps))).size,
      traceCoverage: Math.round(100 * alert.hits.filter(hit => traces.has(hit.hit_id)).length / alert.hits.length),
      evidence: new Set(alert.hits.flatMap(hit => hit.evidence)).size, findings: [...new Set(alert.hits.map(hit => hit.reason_code))],
    };
  });
}
export function assessCases(cases: Case[], reviews: Review[]): RiskItem[] {
  return cases.map(entry => {
    const pairs = entry.packet.candidate_pairs;
    const outcome = entry.packet.case_outcome.splink_with_guard;
    const base = outcome === "LINK" ? 75 : ["NO_LINK", "NO_CANDIDATE"].includes(outcome) ? 10 : 40;
    const missing = entry.recommendation?.missing_evidence.length ?? 0;
    const drivers: RiskDriver[] = [{ label: "Screening outcome", points: base, detail: outcome.replaceAll("_", " ") }];
    if (missing && base !== 10) drivers.push({ label: "Evidence gaps", points: Math.min(15, missing * 5), detail: entry.recommendation!.missing_evidence.map(item => item.finding).join("; ") });
    if (entry.packet.sanctions_list && base !== 10) drivers.push({ label: "List entry requires review", points: 15, detail: `Check the current entry in ${entry.packet.sanctions_list.name}.` });
    const score = Math.min(100, drivers.reduce((sum, driver) => sum + driver.points, 0));
    return { id: entry.id, title: entry.title, score, band: riskBand(score), drivers, nextAction: entry.recommendation?.suggested_next_check ?? "Review the evidence and record a senior decision.", status: reviewStage(reviews, entry.id) === "resolved" ? "Closed" : "Open", hits: pairs.length, unresolved: pairs.filter(pair => pair.decisions.splink_with_guard.includes("REVIEW")).length, same: pairs.filter(pair => pair.decisions.splink_with_guard === "LINK").length, gaps: missing, traceCoverage: pairs.length ? Math.round(100 * pairs.filter(pair => pair.scores.splink !== null).length / pairs.length) : 0, evidence: new Set(entry.recommendation?.evidence_ids ?? []).size, findings: [outcome] };
  });
}
export function riskSummary(items: RiskItem[]) {
  const open = items.filter(item => item.status === "Open");
  return { total: items.length, open: open.length, closed: items.filter(item => item.status === "Closed").length, clear: items.filter(item => item.status === "Clear").length,
    average: items.length ? Math.round(items.reduce((sum, item) => sum + item.score, 0) / items.length) : 0,
    highOpen: open.filter(item => item.band === "High").length,
    missingTrace: items.filter(item => item.traceCoverage < 100).length,
    unresolved: items.reduce((sum, item) => sum + item.unresolved, 0),
    bands: Object.fromEntries(riskBands.map(band => [band, { total: items.filter(item => item.band === band).length, open: open.filter(item => item.band === band).length }])) as Record<RiskBand, { total: number; open: number }>,
  };
}
export function riskCsv(items: RiskItem[]): string {
  // Prevent spreadsheet formula interpretation when exporting source-provided strings.
  const cell = (value: string | number) => `"${String(value).replace(/^[=+@\-\t\r]/, "'$&").replaceAll('"', '""')}"`;
  return [["Alert", "Customer", "Score", "Band", "Status", "Hits", "Unresolved hits", "Trace coverage %", "Evidence IDs", "Model"], ...items.map(item => [item.id, item.title, item.score, item.band, item.status, item.hits, item.unresolved, item.traceCoverage, item.evidence, riskModelVersion])].map(row => row.map(cell).join(",")).join("\r\n");
}
