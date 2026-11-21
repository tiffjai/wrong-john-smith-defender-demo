import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import RiskDashboard from "../app/risk-dashboard";
import type { RiskItem } from "../lib/risk";
const item = (id: string, score: number, band: RiskItem["band"], status: RiskItem["status"] = "Open"): RiskItem => ({ id, title: `Customer ${id}`, score, band, status, hits: 2, unresolved: 1, same: 0, gaps: 1, traceCoverage: 50, evidence: 2, findings: ["INSUFFICIENT_DATA"], drivers: [{ label: "Identity evidence", points: score, detail: "Record requires review." }], nextAction: "Inspect source documents." });
const items = [item("A", 90, "High"), item("B", 45, "Medium"), item("C", 10, "Low", "Clear"), item("D", 75, "High", "Closed")];
afterEach(cleanup);
it("filters the register while preserving portfolio totals and opens the exact review", () => {
  const open = vi.fn(); render(<RiskDashboard items={items} source="Test run" onOpen={open}/>);
  fireEvent.change(screen.getByLabelText("Risk level"), { target: { value: "High" } });
  fireEvent.change(screen.getByLabelText("Review status"), { target: { value: "Open" } });
  expect(screen.getByText("1 of 4 alerts")).toBeDefined();
  const table = screen.getByRole("table");
  expect(within(table).queryByText("Customer D")).toBeNull();
  fireEvent.click(within(table).getByRole("button", { name: "Open review" }));
  expect(open).toHaveBeenCalledWith("A");
  fireEvent.change(screen.getByLabelText("Search risk register"), { target: { value: "missing customer" } });
  expect(screen.getByText("No alerts match these filters.")).toBeDefined();
  fireEvent.click(screen.getByRole("button", { name: "Reset filters" }));
  expect(screen.getByText("4 of 4 alerts")).toBeDefined();
});
it("shows the selected score factors and distinguishes closed high risk from open work", () => {
  render(<RiskDashboard items={items} source="Test run" onOpen={vi.fn()}/>);
  fireEvent.click(screen.getByRole("button", { name: "Inspect risk D" }));
  const explanation = screen.getByLabelText("Risk score explanation");
  expect(within(explanation).getByText("Customer D")).toBeDefined();
  expect(within(explanation).getByText("+75")).toBeDefined();
  expect(within(explanation).getByText(/recorded closure rationale/)).toBeDefined();
  expect(within(screen.getByLabelText("Risk operations summary")).getByText("1 high risk")).toBeDefined();
});
it("paginates the full register and resets to the first matching page after filtering", () => {
  render(<RiskDashboard items={Array.from({ length: 55 }, (_, i) => item(String(i).padStart(2, "0"), 90, "High"))} source="Large run" onOpen={vi.fn()}/>);
  expect(within(screen.getByRole("table")).getAllByRole("row")).toHaveLength(26);
  fireEvent.click(screen.getByRole("button", { name: "Next" }));
  expect(screen.getByText("Page 2 of 3")).toBeDefined();
  fireEvent.change(screen.getByLabelText("Search risk register"), { target: { value: "Customer 54" } });
  expect(screen.getByText("Page 1 of 1")).toBeDefined();
  expect(within(screen.getByRole("table")).getByText("Customer 54")).toBeDefined();
});
it("handles an empty run without invalid chart values", () => {
  render(<RiskDashboard items={[]} source="Empty run" onOpen={vi.fn()}/>);
  expect(screen.getByText("No alerts match these filters.")).toBeDefined();
  expect((screen.getByRole("button", { name: "Export filtered risk report" }) as HTMLButtonElement).disabled).toBe(true);
  expect(screen.getByRole("img").getAttribute("aria-label")).toBe("High: 0, Medium: 0, Low: 0");
});
