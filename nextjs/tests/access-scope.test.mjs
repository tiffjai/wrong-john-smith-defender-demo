import test from "node:test";
import assert from "node:assert/strict";
import { hasAllDataAccess, accessScopeLabel } from "../lib/access-scope.ts";

test("global scope requires both senior role and explicit all-data assignment", () => {
  assert.equal(hasAllDataAccess({booking_entity: "UK", review_role: "reviewer", data_scope: "all"}), true);
  for (const profile of [undefined, {booking_entity: "UK", review_role: "reviewer"}, {booking_entity: "UK", review_role: "analyst", data_scope: "all"}, {booking_entity: "US", review_role: "reviewer", data_scope: "entity"}]) assert.equal(hasAllDataAccess(profile), false);
});

test("scope labels distinguish all-data seniors from entity-scoped accounts", () => {
  assert.equal(accessScopeLabel({booking_entity: "UK", review_role: "reviewer", data_scope: "all"}), "All booking entities · UK & US");
  assert.equal(accessScopeLabel({booking_entity: "US", review_role: "analyst"}), "US booking entity");
});
