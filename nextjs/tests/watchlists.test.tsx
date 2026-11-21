import { useState } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import WatchlistsPanel from "../app/watchlists";
import {
  analyst, customerKeys, demoNotice, initialRescreenState, recordDecision, senior,
  type CustomerKey, type RescreenState,
} from "../lib/rescreen";

afterEach(() => cleanup());

const analystReason: Record<CustomerKey, string> = {
  A: "Independent verified registry evidence identifies two separate people.",
  B: "The verified customer and watchlist dates of birth conflict in V1.",
};

function closeBoth(): RescreenState {
  return customerKeys.reduce((current, customer) => {
    const proposed = recordDecision(current, {
      customer, kind: "proposed", actor: analyst, rationale: analystReason[customer], at: "2026-11-21T09:00:00Z",
    });
    return recordDecision(proposed, {
      customer, kind: "approved", actor: senior, rationale: "Approved by a different senior reviewer.", at: "2026-11-21T09:05:00Z",
    });
  }, initialRescreenState);
}

function Harness() {
  const [state, setState] = useState(closeBoth);
  return <WatchlistsPanel state={state} onState={setState} />;
}

function version(label: "Loaded version" | "Screened version") {
  return screen.getByText(label).closest(".version-pill")?.textContent ?? "";
}

describe("Watchlists page", () => {
  it("loads V2 without screening, then reopens B once", () => {
    render(<Harness />);
    expect(screen.getByText(demoNotice)).toBeTruthy();
    expect(version("Loaded version")).toContain("V1");
    expect(version("Screened version")).toContain("V1");
    expect(screen.getByRole("button", { name: "Load V2" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Rescreen" })).toBeTruthy();
    expect(screen.getByTestId("reopen-count").textContent).toBe("Reopen events: 0");

    fireEvent.change(screen.getByLabelText("Retrieval threshold"), { target: { value: "95" } });
    expect(screen.getAllByText("Not retrieved")).toHaveLength(2);
    expect(screen.getAllByText("0.58%")).toHaveLength(2);

    fireEvent.click(screen.getByRole("button", { name: "Load V2" }));
    expect(version("Loaded version")).toContain("V2");
    expect(version("Screened version")).toContain("V1");
    expect(screen.getByRole("status").textContent).toMatch(/Rescreen has not run/);
    expect(screen.getByText("RESCREEN-A: Closed · Approved false positive")).toBeTruthy();
    expect(screen.getByText("RESCREEN-B: Closed · Approved false positive")).toBeTruthy();
    expect(screen.getByTestId("reopen-count").textContent).toBe("Reopen events: 0");

    fireEvent.click(screen.getByRole("button", { name: "Rescreen" }));
    expect(version("Screened version")).toContain("V2");
    expect(screen.getByText("RESCREEN-A: Closed · Approved false positive")).toBeTruthy();
    expect(screen.getByText("RESCREEN-B: Reopened · Human review")).toBeTruthy();
    expect(screen.getByTestId("reopen-count").textContent).toBe("Reopen events: 1");
    expect(screen.getByRole("status").textContent).toMatch(/1 new reopening/);

    fireEvent.click(screen.getByRole("button", { name: "Rescreen" }));
    expect(screen.getByTestId("reopen-count").textContent).toBe("Reopen events: 1");
    expect(screen.getByRole("status").textContent).toMatch(/0 new reopenings/);

    fireEvent.click(screen.getByRole("button", { name: "Load V2" }));
    expect(screen.getByRole("status").textContent).toMatch(/No rescreen was run/);
    expect(screen.getByTestId("reopen-count").textContent).toBe("Reopen events: 1");
    expect(screen.getAllByText(/RESCREEN-A/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/RESCREEN-B/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/DEMO-ANALYST-1/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/DEMO-REVIEWER-2/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/RS-A-REGISTRY-01/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/RS-WL-DOB-V1/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/RS-WL-DOB-V2/).length).toBeGreaterThan(0);
  });
});
