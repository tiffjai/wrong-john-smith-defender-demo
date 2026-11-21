import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
vi.mock("../app/login/actions", () => ({ signOut: vi.fn() }));
import Dashboard from "../app/dashboard";
import benchmark from "../data/benchmark.json";
import { fixtures } from "../lib/fixtures";

afterEach(cleanup);
it("opens identity review in an authenticated workspace without replacing live cases", () => {
  render(<Dashboard mode="supabase" cases={fixtures} benchmark={benchmark} reviews={[]} notes={[]} profile={{ booking_entity: "UK", review_role: "analyst" }}/>);
  fireEvent.click(screen.getByRole("button", { name: "Identity review" }));
  expect(screen.getByRole("heading", { name: "Same person or not?" })).toBeDefined();
  expect(screen.getByRole("button", { name: "Import predictions" })).toBeDefined();
  expect(screen.getByRole("note").textContent).toContain("does not change live case decisions");
  fireEvent.click(screen.getByRole("button", { name: "Screening queue" }));
  expect(screen.getByRole("textbox", { name: "Filter cases" })).toBeDefined();
});

it("opens the selected imported alert from the risk dashboard", () => {
  render(<Dashboard mode="supabase" cases={fixtures} benchmark={benchmark} reviews={[]} notes={[]} profile={{ booking_entity: "UK", review_role: "reviewer", data_scope: "all" }} screeningRun={{ source: "Test import", storage: "supabase", synthetic: false, predictions: [{ alert_id: "ALERT-ONE", hit_id: "HIT-ONE", customer_record_id: "CUS-ONE", decision: "REVIEW", reason_code: "INSUFFICIENT_DATA", reason: "Need evidence.", evidence: ["KYC-ONE"] }, { alert_id: "ALERT-TWO", hit_id: "HIT-TWO", customer_record_id: "CUS-TWO", decision: "SAME_ENTITY", reason_code: "NAME_DOB_MATCH", reason: "Identity agrees.", evidence: ["KYC-TWO"] }], traces: {} }}/>);
  fireEvent.click(screen.getAllByRole("button", { name: "Open review" })[0]);
  expect(screen.getByText("ALERT-TWO / HIT-TWO")).toBeDefined();
  expect(screen.getByRole("button", { name: "Close review — no escalation required" })).toBeDefined();
});

it("updates dashboard closure counts after a senior saves an imported review", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ alert_id: "ALERT-CLOSE", rationale: "No suspicion found.", created_at: "2026-11-21T14:00:00Z" }) }));
  render(<Dashboard mode="supabase" cases={fixtures} benchmark={benchmark} reviews={[]} notes={[]} profile={{ booking_entity: "UK", review_role: "reviewer", data_scope: "all" }} screeningRun={{ source: "Closure test", importId: "a".repeat(64), storage: "supabase", synthetic: false, predictions: [{ alert_id: "ALERT-CLOSE", hit_id: "HIT-CLOSE", customer_record_id: "CUS-CLOSE", decision: "SAME_ENTITY", reason_code: "NAME_DOB_MATCH", reason: "Identity agrees.", evidence: ["KYC-CLOSE"] }], traces: {} }}/>);
  fireEvent.click(screen.getByRole("button", { name: "Open review" }));
  fireEvent.change(screen.getByLabelText("Closure rationale"), { target: { value: "No suspicion found." } });
  fireEvent.click(screen.getByRole("button", { name: "Close review — no escalation required" }));
  await screen.findByText("Closed — no escalation required");
  fireEvent.click(screen.getByRole("button", { name: "Risk dashboard" }));
  const summary = screen.getByLabelText("Risk operations summary");
  expect(within(summary).getByText("0 high risk")).toBeDefined();
  expect(within(summary).getByRole("button", { name: /Senior closures/ }).textContent).toContain("Senior closures1");
  expect(within(screen.getByRole("table")).getByText("Closed")).toBeDefined();
  expect(within(screen.getByRole("table")).getByText("85/100")).toBeDefined();
  vi.unstubAllGlobals();
});
