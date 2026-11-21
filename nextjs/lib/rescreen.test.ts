import { describe, expect, it } from "vitest";
import {
  analyst, auditReport, compareFields, customerKeys, initialRescreenState, loadWatchlist,
  normaliseName, readRescreenState, recordDecision, rescreen, retrievalScore, reviewStage,
  senior, setRetrievalThreshold, tokenSortRatio, type CustomerKey, type RescreenState,
} from "./rescreen";

const analystReason: Record<CustomerKey, string> = {
  A: "Independent verified registry evidence identifies two separate people.",
  B: "The verified customer and watchlist dates of birth conflict in V1.",
};
const seniorReason = "Approved by a different senior reviewer.";

function closeBoth(state = initialRescreenState): RescreenState {
  return customerKeys.reduce((current, customer) => {
    const proposed = recordDecision(current, {
      customer, kind: "proposed", actor: analyst, rationale: analystReason[customer], at: "2026-11-21T09:00:00Z",
    });
    return recordDecision(proposed, {
      customer, kind: "approved", actor: senior, rationale: seniorReason, at: "2026-11-21T09:05:00Z",
    });
  }, state);
}

describe("retrieval threshold and score labels", () => {
  it("normalises names and scores the Chan romanisations at 91.6667", () => {
    expect(normaliseName("Chan Wai-Man")).toBe("chan wai man");
    expect(normaliseName("CHAN Wai Man")).toBe("chan wai man");
    expect(tokenSortRatio("Chan Wai Man", "CHAN Wai Man")).toBe(100);
    expect(tokenSortRatio("Chan Wai Man", "Chan Wai Mun")).toBe(91.6667);
  });

  it("labels retrieval similarity separately from identity probability", () => {
    const low = retrievalScore("B", "V1", 90);
    const high = retrievalScore("B", "V2", 90);
    expect(low.retrievalSimilarityLabel).toBe("Retrieval similarity");
    expect(low.identityProbabilityLabel).toBe("Identity probability");
    expect(low.retrievalSimilarityLabel).not.toBe(low.identityProbabilityLabel);
    expect(low.retrievalSimilarity).toBe(91.6667);
    expect(low.identityProbability).toBeCloseTo(0.005833842, 8);
    expect(low.retrieved).toBe(true);
    expect(high.retrievalSimilarity).toBe(100);
    expect(high.identityProbability).toBeCloseTo(0.999905061, 8);
    expect(high.customerEvidenceId).toBe("RS-B-ALIAS-01");
    expect(high.watchlistEvidenceId).toBe("RS-WL-ALIAS-V2");
    expect(high.retrievalSimilarity).not.toBe(high.identityProbability);
  });

  it("drops V1 candidates above 91.6667 and still retrieves the V2 alias match", () => {
    expect(retrievalScore("A", "V1", 90).retrieved).toBe(true);
    expect(retrievalScore("B", "V1", 95).retrieved).toBe(false);
    expect(retrievalScore("A", "V1", 95).retrieved).toBe(false);
    expect(retrievalScore("A", "V2", 95).retrieved).toBe(true);
    expect(retrievalScore("B", "V2", 95).retrieved).toBe(true);
    expect(retrievalScore("A", "V2", 95).watchlistEvidenceId).toBe("RS-WL-ALIAS-V2");
    const below = retrievalScore("B", "V1", 95);
    const above = retrievalScore("B", "V1", 90);
    expect(below.identityProbability).toBe(above.identityProbability);
    expect(below.retrievalSimilarity).toBe(above.retrievalSimilarity);
  });
});

describe("load and rescreen", () => {
  it("loads V2 without changing the screened version or events", () => {
    const closed = closeBoth();
    const loaded = loadWatchlist(closed, "V2");
    expect(loaded.result).toBe("ACTIVATED");
    expect(loaded.state.loaded).toBe("V2");
    expect(loaded.state.snapshot).toBe("V1");
    expect(loaded.state.events).toEqual(closed.events);
    expect(reviewStage(loaded.state.events, "A")).toBe("closed");
    expect(reviewStage(loaded.state.events, "B")).toBe("closed");
    expect(loaded.state.events.some((event) => event.kind === "reopened")).toBe(false);
  });

  it("keeps A closed, reopens B once, and ignores a repeated load or rescreen", () => {
    const loaded = loadWatchlist(closeBoth(), "V2").state;
    const first = rescreen(loaded, loaded.loaded, "2026-11-21T10:00:00Z");
    expect(first.state.loaded).toBe("V2");
    expect(first.state.snapshot).toBe("V2");
    expect(first.reopened).toBe(1);
    expect(first.retained).toBe(1);
    expect(reviewStage(first.state.events, "A")).toBe("closed");
    expect(reviewStage(first.state.events, "B")).toBe("reopened");
    expect(first.state.events.filter((event) => event.kind === "reopened")).toHaveLength(1);
    const retained = first.state.events.find((event) => event.customer === "A" && event.kind === "closure_retained");
    expect(retained?.evidence).toEqual(["RS-A-REGISTRY-01"]);
    expect(retained?.rationale).toContain("independent registry exclusion");
    expect(retained?.basis).toBe("independent_identity");

    const second = rescreen(first.state, "V2", "2026-11-21T11:00:00Z");
    expect(second.reopened).toBe(0);
    expect(second.state.events.filter((event) => event.kind === "reopened")).toHaveLength(1);
    expect(second.state.events).toEqual(first.state.events);
    const again = loadWatchlist(second.state, "V2");
    expect(again.result).toBe("NO_UPDATE");
    expect(again.state.snapshot).toBe("V2");
    expect(again.state.events.filter((event) => event.kind === "reopened")).toHaveLength(1);
  });

  it("does not let the retrieval threshold rescreen or rewrite versions", () => {
    const loaded = loadWatchlist(closeBoth(), "V2").state;
    const adjusted = setRetrievalThreshold(loaded, 95);
    expect(adjusted.snapshot).toBe("V1");
    expect(adjusted.loaded).toBe("V2");
    expect(adjusted.events).toBe(loaded.events);
    expect(adjusted.retrievalThreshold).toBe(95);
  });

  it("rejects self-approval by the proposing analyst", () => {
    const proposed = recordDecision(initialRescreenState, {
      customer: "A", kind: "proposed", actor: analyst, rationale: analystReason.A, at: "2026-11-21T09:00:00Z",
    });
    expect(() => recordDecision(proposed, {
      customer: "A", kind: "approved", actor: analyst, rationale: seniorReason, at: "2026-11-21T09:05:00Z",
    })).toThrow(/different senior reviewer/);
    expect(() => recordDecision(proposed, {
      customer: "A", kind: "approved", actor: { id: analyst.id, name: "Same person", role: "senior" },
      rationale: seniorReason, at: "2026-11-21T09:05:00Z",
    })).toThrow(/different senior reviewer/);
    const approved = recordDecision(proposed, {
      customer: "A", kind: "approved", actor: senior, rationale: seniorReason, at: "2026-11-21T09:05:00Z",
    });
    expect(reviewStage(approved.events, "A")).toBe("closed");
  });
});

describe("evidence and audit", () => {
  it("keeps original and current snapshots and the registry exclusion", () => {
    const v1 = compareFields("B", "V1").find((row) => row.field === "dob");
    const v2 = compareFields("B", "V2").find((row) => row.field === "dob");
    expect(v1).toMatchObject({ mark: "conflicting", customer: { value: "1991-06-14", evidenceId: "RS-B-DOB-01" }, watchlist: { value: "1987-09-03", evidenceId: "RS-WL-DOB-V1", snapshotId: "V1" } });
    expect(v2).toMatchObject({ mark: "supporting", watchlist: { value: "1991-06-14", evidenceId: "RS-WL-DOB-V2", snapshotId: "V2" } });
    expect(compareFields("B", "V1").find((row) => row.field === "alias")?.mark).toBe("missing");
    expect(compareFields("B", "V2").find((row) => row.field === "alias")).toMatchObject({
      mark: "supporting", customer: { evidenceId: "RS-B-ALIAS-01" }, watchlist: { value: "Chan Wai Man", evidenceId: "RS-WL-ALIAS-V2" },
    });
    expect(compareFields("A", "V1").find((row) => row.field === "alias")?.mark).toBe("missing");
    const registry = compareFields("A", "V2").find((row) => row.field === "registry");
    expect(registry?.mark).toBe("supporting");
    expect(registry?.customer.evidenceId).toBe("RS-A-REGISTRY-01");
    expect(compareFields("B", "V2").some((row) => row.field === "registry")).toBe(false);
  });

  it("exports both cases with decisions, identities, reasons and rescreen events", () => {
    const screened = rescreen(loadWatchlist(closeBoth(), "V2").state, "V2", "2026-11-21T10:00:00Z").state;
    const report = auditReport(screened);
    const text = JSON.stringify(report);
    expect(report.enrolledCustomers).toEqual(["RESCREEN-A", "RESCREEN-B"]);
    expect(report.loadedVersion).toBe("V2");
    expect(report.screenedVersion).toBe("V2");
    expect(report.supabasePersistence).toBe(false);
    expect(report.officialFeedConnected).toBe(false);
    expect(report.automaticBankWideScreening).toBe(false);
    expect(text).toContain("RS-A-REGISTRY-01");
    expect(text).toContain("RS-WL-DOB-V1");
    expect(text).toContain("RS-WL-DOB-V2");
    expect(text).toContain("RS-B-DOB-01");
    expect(text).toContain("RS-B-ALIAS-01");
    expect(text).toContain("RS-WL-ALIAS-V2");
    expect(text).toContain("DEMO-ANALYST-1");
    expect(text).toContain("DEMO-REVIEWER-2");
    expect(text).toContain(analystReason.A);
    expect(text).toContain(analystReason.B);
    expect(text).toContain(seniorReason);
    expect(text).toContain("independent registry exclusion");
    expect(report.cases.find((entry) => entry.caseId === "RESCREEN-B")?.rescreenEvents.filter((event) => event.kind === "reopened")).toHaveLength(1);
    expect(report.cases.find((entry) => entry.caseId === "RESCREEN-A")?.rescreenEvents.map((event) => event.kind)).toEqual(["closure_retained"]);
    expect(report.reviewerIdentities.map((actor) => actor.id)).toEqual(expect.arrayContaining(["DEMO-ANALYST-1", "DEMO-REVIEWER-2", "DEMO-SYSTEM"]));
  });

  it("reads an older saved rehearsal without screening it again", () => {
    const restored = readRescreenState(JSON.stringify({ snapshot: "V1", events: [] }));
    expect(restored).toMatchObject({ snapshot: "V1", loaded: "V1", events: [] });
  });
});
