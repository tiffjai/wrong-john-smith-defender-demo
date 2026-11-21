import { cleanup, fireEvent, render, screen, within, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import EntityWorkspace from "../app/entity-workspace";
import type { Prediction, ScreeningRun } from "../lib/entity-resolution";

afterEach(cleanup);
const different: Prediction = { alert_id: "LATEST-A", hit_id: "LATEST-H1", customer_record_id: "LATEST-C1", decision: "DIFFERENT_ENTITY", reason_code: "DOB_MISMATCH", reason: "Verified dates contradict.", evidence: ["LATEST-KYC"] };
const run: ScreeningRun = { source: "Latest test snapshot", synthetic: false, generatedAt: "2026-11-21T13:00:00Z", predictions: [different, { ...different, hit_id: "LATEST-H2", decision: "REVIEW", reason_code: "INSUFFICIENT_DATA", reason: "A date is missing." }, { ...different, alert_id: "LATEST-B", hit_id: "LATEST-H3", customer_record_id: "LATEST-C2" }], traces: { "LATEST-H1:LATEST-C1": { customer: { name: "Alex Latest", dob: [1980], countries: ["UK"], verified: true, records: ["LATEST-C1"] }, watchlist: { name: "Alex Namesake", dobs: [ [1950] ], countries: ["UK"], report: null }, path: ["LATEST-C1", "LATEST-KYC"], gaps: [] } } };

describe("latest dataset screening queue", () => {
  it("groups hits into alerts and keeps mixed alerts open when filtered to different hits", () => {
    render(<EntityWorkspace initialRun={run} queueMode/>);
    expect(screen.getByText("3 hits · 2 alerts")).toBeDefined();
    expect(screen.getByText("2 alerts")).toBeDefined();
    expect(screen.getByRole("button", { name: /LATEST-A.*Alex Latest.*Open.*2 hits/ })).toBeDefined();
    fireEvent.change(screen.getByLabelText("Identity decision"), { target: { value: "DIFFERENT_ENTITY" } });
    expect(screen.getByRole("button", { name: /LATEST-A.*Alex Latest.*Open.*2 hits/ })).toBeDefined();
    fireEvent.change(screen.getByLabelText("Alert status"), { target: { value: "CLEAR" } });
    expect(screen.queryByRole("button", { name: /LATEST-A.*Alex Latest/ })).toBeNull();
    expect(screen.getByRole("button", { name: /LATEST-B.*LATEST-C2.*Clear/ })).toBeDefined();
  });
  it("searches customer names and lets reviewers open a sibling hit", () => {
    render(<EntityWorkspace initialRun={run} queueMode/>);
    fireEvent.change(screen.getByRole("textbox", { name: "Search screening hits" }), { target: { value: "Alex Latest" } });
    expect(screen.getByText("1 alerts")).toBeDefined();
    fireEvent.click(screen.getByRole("button", { name: "LATEST-H2 · Needs review" }));
    expect(within(screen.getByLabelText("Identity evidence")).getByText("A date is missing.", { selector: "p" })).toBeDefined();
    expect(screen.queryByRole("button", { name: "Import predictions" })).toBeNull();
  });
});

it("allows seniors to close a mixed alert without changing identity findings", async () => {
  render(<EntityWorkspace initialRun={run} queueMode allowClose/>);
  const close = screen.getByRole("button", { name: "Close review — no escalation required" });
  expect((close as HTMLButtonElement).disabled).toBe(true);
  fireEvent.change(screen.getByLabelText("Closure rationale"), { target: { value: "All hits reviewed; no suspicion or escalation needed." } });
  fireEvent.click(close);
  await waitFor(() => expect(screen.getByText("Closed — no escalation required")).toBeDefined());
  expect(screen.getByRole("button", { name: /LATEST-A.*Closed.*2 hits/ })).toBeDefined();
  expect(screen.getByRole("button", { name: "LATEST-H2 · Needs review" })).toBeDefined();
  fireEvent.change(screen.getByLabelText("Alert status"), { target: { value: "OPEN" } });
  expect(screen.queryByRole("button", { name: /LATEST-A.*2 hits/ })).toBeNull();
});
it("keeps closure unavailable to junior users", () => {
  render(<EntityWorkspace initialRun={run} queueMode/>);
  expect(screen.queryByRole("button", { name: "Close review — no escalation required" })).toBeNull();
});
it("does not mark the alert closed when cloud saving fails", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, json: async () => ({ error: "Could not close the review." }) }));
  render(<EntityWorkspace initialRun={{ ...run, storage: "supabase", importId: "a".repeat(64) }} queueMode allowClose/>);
  fireEvent.change(screen.getByLabelText("Closure rationale"), { target: { value: "No suspicion found." } });
  fireEvent.click(screen.getByRole("button", { name: "Close review — no escalation required" }));
  await waitFor(() => expect(screen.getByRole("status").textContent).toBe("Could not close the review."));
  expect(screen.getByRole("button", { name: /LATEST-A.*Open.*2 hits/ })).toBeDefined();
  vi.unstubAllGlobals();
});
