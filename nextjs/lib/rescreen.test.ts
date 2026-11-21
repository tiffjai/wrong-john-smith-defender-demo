import assert from "node:assert/strict";
import { test } from "node:test";
import {
  analyst, initialRescreenState, recordDecision, rescreen, reviewStage, senior, type RescreenState,
} from "./rescreen";

const at = "2026-11-21T09:00:00.000Z";

function approveBoth(state: RescreenState): RescreenState {
  state = recordDecision(state, { customer: "A", kind: "proposed", actor: analyst, rationale: "Independent registry exclusion for customer A.", at });
  state = recordDecision(state, { customer: "B", kind: "proposed", actor: analyst, rationale: "Verified dates of birth conflict in V1.", at });
  state = recordDecision(state, { customer: "A", kind: "approved", actor: senior, rationale: "Senior approval for customer A.", at });
  return recordDecision(state, { customer: "B", kind: "approved", actor: senior, rationale: "Senior approval for customer B.", at });
}

test("V2 keeps customer A closed, reopens customer B once, and leaves the approvals in history", () => {
  const approved = approveBoth(initialRescreenState);
  const original = approved.events.map((event) => structuredClone(event));
  const first = rescreen(approved, "V2", "2026-11-21T10:00:00.000Z");

  assert.equal(first.state.snapshot, "V2");
  assert.equal(first.reopened, 1);
  assert.equal(first.retained, 1);
  assert.equal(reviewStage(first.state.events, "A"), "closed");
  assert.equal(reviewStage(first.state.events, "B"), "reopened");
  assert.equal(first.state.events.filter((event) => event.kind === "closure_retained" && event.customer === "A").length, 1);
  assert.equal(first.state.events.filter((event) => event.kind === "reopened" && event.customer === "B").length, 1);
  assert.deepEqual(first.state.events.slice(0, original.length), original);

  const second = rescreen(first.state, "V2", "2026-11-21T11:00:00.000Z");
  assert.equal(second.reopened, 0);
  assert.equal(second.state.events.filter((event) => event.kind === "reopened").length, 1);
  assert.equal(second.state.events.length, first.state.events.length);
  assert.deepEqual(second.state.events.slice(0, original.length), original);
  assert.equal(second.state.events.find((event) => event.customer === "B" && event.kind === "approved")?.rationale, "Senior approval for customer B.");
});

test("a rejected decision does not rewrite review history", () => {
  const proposed = recordDecision(initialRescreenState, {
    customer: "A", kind: "proposed", actor: analyst, rationale: "Propose a closure.", at,
  });
  const before = proposed.events.map((event) => structuredClone(event));
  assert.throws(() => recordDecision(proposed, {
    customer: "A", kind: "approved", actor: analyst, rationale: "Self approval.", at,
  }), /senior reviewer/);
  assert.deepEqual(proposed.events, before);
  assert.throws(() => rescreen(proposed, "V2", at), /Approve both V1 proposals/);
  assert.equal(proposed.snapshot, "V1");
  assert.deepEqual(proposed.events, before);
});
