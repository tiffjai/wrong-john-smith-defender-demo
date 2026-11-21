import test from "node:test";
import assert from "node:assert/strict";
import { reviewStage, latestReview } from "../lib/review-queue.ts";

const event = (decision, created_at = "2026-11-21T12:00:00Z") => ({ case_id: "CASE-08", decision, created_at, rationale: "Evidence assessed" });

test("evidence requests remain open; escalation is not completion", () => {
  assert.equal(reviewStage([], "CASE-08"), "pending");
  assert.equal(reviewStage([event("awaiting_evidence")], "CASE-08"), "pending");
  for (const decision of ["escalated_legal", "escalated_mlro", "escalated_sanctions"]) {
    assert.equal(reviewStage([event(decision)], "CASE-08"), "escalated");
  }
  assert.equal(reviewStage([event("resolved")], "CASE-08"), "resolved");
});

test("latest decision determines status independently of fetch order and other cases", () => {
  const history = [event("resolved"), event("awaiting_evidence", "2026-11-21T13:00:00Z")];
  assert.equal(reviewStage(history, "CASE-08"), "pending");
  assert.equal(reviewStage(history.toReversed(), "CASE-08"), "pending");
  assert.equal(reviewStage(history, "CASE-11"), "pending");
  assert.equal(latestReview(history, "CASE-08").decision, "awaiting_evidence");
});
