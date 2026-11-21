import { cleanup, fireEvent, render, screen } from "@testing-library/react";
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
