// @vitest-environment node
import { beforeEach, expect, it, vi } from "vitest";
const state = vi.hoisted(() => ({ user: true, role: "reviewer", scope: "all", insert: vi.fn() }));
vi.mock("../lib/supabase", () => ({
  cloudMode: true, config: () => ({}), serverClient: async () => ({
    auth: { getClaims: async () => ({ data: state.user ? { claims: { sub: "senior" } } : null }) },
    from: (table: string) => {
      const query = { select: () => query, eq: () => query,
        maybeSingle: async () => ({ data: { review_role: state.role, data_scope: state.scope, booking_entity: "UK" } }),
        insert: (value: unknown) => { state.insert(value); return query; },
        single: async () => ({ data: { alert_id: "A", rationale: "Reviewed", created_at: "2026-11-21" }, error: null }) };
      return query;
    },
  }),
}));
import { POST } from "../app/api/screening-reviews/route";
const request = (rationale = "Reviewed") => new Request("http://localhost/api/screening-reviews", { method: "POST", body: JSON.stringify({ import_id: "a".repeat(64), alert_id: "A", rationale }) });
beforeEach(() => { state.user = true; state.role = "reviewer"; state.scope = "all"; state.insert.mockClear(); });
it("requires authentication and senior dataset access", async () => {
  state.user = false; expect((await POST(request())).status).toBe(401);
  state.user = true; state.role = "analyst"; expect((await POST(request())).status).toBe(403);
  state.role = "reviewer"; state.scope = "entity"; expect((await POST(request())).status).toBe(403);
  expect(state.insert).not.toHaveBeenCalled();
});
it("requires a rationale and saves an authenticated senior closure", async () => {
  expect((await POST(request("  "))).status).toBe(400);
  expect(state.insert).not.toHaveBeenCalled();
  expect((await POST(request())).status).toBe(201);
  expect(state.insert).toHaveBeenCalledWith({ import_id: "a".repeat(64), alert_id: "A", rationale: "Reviewed" });
});
