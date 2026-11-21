// @vitest-environment node
import { beforeEach, expect, test, vi } from "vitest";

const state = vi.hoisted(() => ({ profile: { booking_entity: "UK", review_role: "reviewer", data_scope: "all" }, readFile: vi.fn(), imported: null as null | { payload: object }, tables: [] as string[] }));
vi.mock("node:fs/promises", () => ({ readFile: state.readFile }));
vi.mock("../app/dashboard", () => ({ default: () => null }));
vi.mock("../app/login/actions", () => ({ signOut: vi.fn() }));
vi.mock("../lib/supabase", () => ({
  cloudMode: true, config: () => ({ url: "https://example.supabase.co", key: "sb_publishable_test" }),
  serverClient: async () => ({
    auth: { getClaims: async () => ({ data: { claims: { sub: "user-1" } } }) },
    from: (table: string) => {
      state.tables.push(table);
      const query = {
        select: () => query, eq: () => query, limit: () => query,
        maybeSingle: async () => ({ data: table === "analyst_profiles" ? state.profile : state.imported, error: null }),
        order: () => query,
        then: (resolve: (value: object) => unknown) => Promise.resolve({ data: [], error: null }).then(resolve),
      };
      return query;
    },
  }),
}));
import Page from "../app/page";

beforeEach(() => {
  state.readFile.mockReset();
  state.tables = [];
  state.imported = null;
  state.readFile.mockResolvedValue(JSON.stringify({ source: "Local run", synthetic: false, predictions: [], traces: {} }));
});

test("all-data Senior receives the protected cloud import and FEBRL4 benchmark", async () => {
  state.profile = { booking_entity: "UK", review_role: "reviewer", data_scope: "all" };
  state.imported = { payload: { source: "Cloud run", synthetic: false, predictions: [], traces: {} } };
  const page = await Page();
  expect(page.props.screeningRun.source).toBe("Cloud run");
  expect(page.props.screeningRun.storage).toBe("supabase");
  expect(state.readFile).not.toHaveBeenCalled();
  expect(page.props.benchmark.dataset).toBe("FEBRL4");
  expect(page.props.benchmark.leftRecords + page.props.benchmark.rightRecords).toBe(10000);
});

test("all-data Senior without a cloud import never falls back to participant files", async () => {
  state.profile = { booking_entity: "UK", review_role: "reviewer", data_scope: "all" };
  const page = await Page();
  expect(page.props.screeningRun).toBeNull();
  expect(state.readFile).not.toHaveBeenCalled();
});

test.each(["analyst", "reviewer"])("entity-scoped %s never receives the unscoped local dataset", async (review_role) => {
  state.profile = { booking_entity: "UK", review_role, data_scope: "entity" };
  const page = await Page();
  expect(page.props.screeningRun).toBeNull();
  expect(state.readFile).not.toHaveBeenCalled();
  expect(state.tables).not.toContain("screening_imports");
  expect(page.props.benchmark.dataset).toBe("FEBRL4");
});
