// @vitest-environment node
import { describe, expect, it } from "vitest";
import { assessAlerts, assessCases, assessHit, riskBand, riskCsv, riskSummary } from "../lib/risk";
import type { IdentityTrace, Prediction, ScreeningRun } from "../lib/entity-resolution";
import { fixtures } from "../lib/fixtures";
const hit: Prediction = { alert_id: "A", hit_id: "H", customer_record_id: "C", decision: "REVIEW", reason_code: "INSUFFICIENT_DATA", reason: "Missing identity evidence", evidence: ["E"] };
const trace: IdentityTrace = { customer: { name: "Alex", dob: [1980, 1, 1], countries: [], verified: true, records: ["C"] }, watchlist: { name: "Alex", dobs: [], countries: [], report: null }, path: ["C"], gaps: [] };
const run: ScreeningRun = { source: "Test", synthetic: true, predictions: [hit, { ...hit, hit_id: "H2", decision: "SAME_ENTITY", reason_code: "NAME_DOB_MATCH" }], traces: { "H:C": trace, "H2:C": trace } };
describe("screening risk scores", () => {
  it("assigns exact boundary bands", () => {
    expect([0, 34, 35, 69, 70, 100].map(riskBand)).toEqual(["Low", "Low", "Medium", "Medium", "High", "High"]);
  });
  it("scores exclusions low and keeps missing evidence from becoming exclusion evidence", () => {
    expect(assessHit({ ...hit, decision: "DIFFERENT_ENTITY" }).score).toBe(10);
    expect(assessHit(hit, [trace]).score).toBe(40);
    expect(assessHit(hit).score).toBe(50);
    expect(assessHit({ ...hit, decision: "SAME_ENTITY" }, [trace]).score).toBe(75);
  });
  it("caps scores, deduplicates gaps and never double-counts customer ambiguity", () => {
    const result = assessHit({ ...hit, decision: "SAME_ENTITY", customer_record_id: "AMBIGUOUS", evidence: [] }, [{ ...trace, customer: { ...trace.customer, verified: false }, gaps: ["A", "A", "B", "C", "D"] }, trace]);
    expect(result.score).toBe(100);
    expect(result.drivers.filter(driver => driver.label === "Customer ambiguity")).toHaveLength(1);
    expect(result.drivers.find(driver => driver.label === "Evidence gaps")?.points).toBe(15);
  });
  it("uses highest hit per alert and preserves risk on senior closure", () => {
    const before = assessAlerts(run)[0];
    const after = assessAlerts(run, [{ alert_id: "A", rationale: "Reviewed", created_at: "2026-11-21" }])[0];
    expect(before.score).toBe(75); expect(before.status).toBe("Open");
    expect(after.score).toBe(before.score); expect(after.status).toBe("Closed");
    expect(after.traceCoverage).toBe(100); expect(after.evidence).toBe(1);
  });
  it("keeps empty portfolios finite and separates risk from open status", () => {
    expect(riskSummary([])).toMatchObject({ total: 0, average: 0, highOpen: 0 });
    const items = assessAlerts(run, [{ alert_id: "A", rationale: "Reviewed", created_at: "2026-11-21" }]);
    expect(riskSummary(items)).toMatchObject({ total: 1, closed: 1, highOpen: 0, bands: { High: { total: 1, open: 0 } } });
  });
  it("scores every demo fixture in range without altering the packet", () => {
    const snapshot = JSON.stringify(fixtures);
    expect(assessCases(fixtures, []).every(item => item.score >= 0 && item.score <= 100)).toBe(true);
    expect(JSON.stringify(fixtures)).toBe(snapshot);
  });
  it("quotes CSV fields and neutralises formulas from imported names", () => {
    const item = { ...assessAlerts(run)[0], title: '=HYPERLINK("bad")' };
    const csv = riskCsv([item]);
    expect(csv).toContain(`"'=HYPERLINK(""bad"")"`);
    expect(csv).toContain('"screening-triage-v1"');
  });
});
