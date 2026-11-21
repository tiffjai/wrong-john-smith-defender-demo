import { describe, expect, it } from "vitest";
import { groupAlerts, parsePredictions, type Prediction } from "../lib/entity-resolution";
const different: Prediction = { hit_id: "H-1", alert_id: "A-1", decision: "DIFFERENT_ENTITY", reason_code: "DOB_MISMATCH", customer_record_id: "CUS-1", reason: "Dates contradict.", evidence: ["CUS-1"] };
describe("Brief v3 output contract", () => {
  it("leaves a multi-hit alert open when one hit needs review", () => {
    const review: Prediction = { ...different, hit_id: "H-2", decision: "REVIEW", reason_code: "INSUFFICIENT_DATA" };
    expect(groupAlerts([different, review])[0].closed).toBe(false);
    expect(groupAlerts([different, { ...different, hit_id: "H-2" }])[0].closed).toBe(true);
    expect(groupAlerts([{ ...review, decision: "SAME_ENTITY", reason_code: "NAME_DOB_MATCH" }])[0].closed).toBe(false);
  });
  it("imports JSONL with exact evidence IDs", () => {
    expect(parsePredictions(JSON.stringify(different) + "\n")).toEqual([different]);
  });
  it("rejects malformed, duplicate, empty and incompatible reason-code imports", () => {
    expect(() => parsePredictions("{}")).toThrow();
    expect(() => parsePredictions("")).toThrow();
    expect(() => parsePredictions([different, different].map(row => JSON.stringify(row)).join("\n"))).toThrow(/duplicate/);
    expect(() => parsePredictions(JSON.stringify({ ...different, reason_code: "INSUFFICIENT_DATA" }))).toThrow();
  });
});
