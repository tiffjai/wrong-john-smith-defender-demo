import fixtures from "../data/rescreen-fixtures.json";

export type CustomerKey = "A" | "B";
export type Snapshot = "V1" | "V2";
export type Basis = "independent_identity" | "verified_dob_conflict";
export type Role = "analyst" | "senior" | "system";
export type Actor = { id: string; name: string; role: Role };
export type Stage = "candidate" | "pending" | "returned" | "closed" | "reopened" | "awaiting_evidence" | "escalated";
type EventKind = "proposed" | "approved" | "returned" | "closure_retained" | "reopened" | "awaiting_evidence" | "escalated";
export type ReviewEvent = {
  customer: CustomerKey; kind: EventKind; snapshot: Snapshot; actor: Actor; at: string;
  rationale: string; evidence: string[]; basis: Basis;
};
export type RescreenState = { snapshot: Snapshot; events: ReviewEvent[] };
export const initialRescreenState: RescreenState = { snapshot: "V1", events: [] };
export const customerKeys = ["A", "B"] as const;
export const analyst: Actor = { id: "DEMO-ANALYST-1", name: "Demo analyst", role: "analyst" };
export const senior: Actor = { id: "DEMO-REVIEWER-2", name: "Demo senior reviewer", role: "senior" };
const engine: Actor = { id: "DEMO-SYSTEM", name: "Rescreening engine", role: "system" };

export function closureBasis(customer: CustomerKey): Basis {
  return customer === "A" ? "independent_identity" : "verified_dob_conflict";
}

export function basisEvidence(customer: CustomerKey, snapshot: Snapshot, basis = closureBasis(customer)) {
  return basis === "independent_identity" ? [fixtures.independentExclusion.id]
    : [fixtures.customers[customer].dobId, fixtures.versions[snapshot].dobId];
}

function basisHolds(customer: CustomerKey, basis: Basis, snapshot: Snapshot) {
  if (basis === "independent_identity") return customer === "A";
  return fixtures.customers[customer].dob !== fixtures.versions[snapshot].dob;
}

export function reviewStage(events: ReviewEvent[], customer: CustomerKey): Stage {
  const outcome = events.findLast((event) => event.customer === customer && event.kind !== "closure_retained");
  if (!outcome || outcome.kind === "closure_retained") return "candidate";
  if (outcome.kind === "proposed") return "pending";
  if (outcome.kind === "approved") return "closed";
  return outcome.kind;
}

export function recordDecision(state: RescreenState, cmd: {
  customer: CustomerKey; kind: "proposed" | "approved" | "returned" | "awaiting_evidence" | "escalated";
  actor: Actor; rationale: string; at: string;
}): RescreenState {
  const { customer, kind, actor, at } = cmd;
  const rationale = cmd.rationale.trim();
  if (!rationale || rationale.length > 1000) throw new Error("Provide a rationale of 1 to 1,000 characters.");

  const stage = reviewStage(state.events, customer);
  const proposal = state.events.findLast((event) => event.customer === customer && event.kind === "proposed");
  const snapshot = state.snapshot;
  const basis = proposal?.basis ?? closureBasis(customer);
  let evidence = basisEvidence(customer, snapshot, basis);
  if (kind === "proposed") {
    if (actor.role !== "analyst" || (stage !== "candidate" && stage !== "returned")) throw new Error("An analyst can propose a closure for a candidate or returned case.");
    if (!basisHolds(customer, basis, snapshot)) throw new Error("This closure basis is unsupported in the active snapshot.");
  } else if (kind === "approved" || kind === "returned") {
    if (stage !== "pending" || !proposal || actor.role !== "senior" || actor.id === proposal.actor.id) {
      throw new Error("A different senior reviewer must decide a pending closure.");
    }
    if (proposal.snapshot !== snapshot) throw new Error("Reassess the proposal against the active snapshot.");
    evidence = proposal.evidence;
  } else {
    if (actor.role !== "analyst" || !["reopened", "awaiting_evidence", "escalated"].includes(stage)) {
      throw new Error("An analyst can request evidence or escalate an open rescreening case.");
    }
    evidence = [fixtures.customers[customer].dobId, fixtures.versions[snapshot].dobId];
  }

  return { ...state, events: [...state.events, { customer, kind, snapshot, actor, at, rationale, evidence, basis }] };
}

export function rescreen(state: RescreenState, target: Snapshot, at: string) {
  if (state.snapshot === "V2" && target === "V1") throw new Error("Choose the active snapshot or a newer one.");
  if (state.snapshot === "V1" && target === "V2" && customerKeys.some((customer) => reviewStage(state.events, customer) !== "closed")) {
    throw new Error("Approve both V1 proposals to run the two-closure demo.");
  }

  const events = [...state.events];
  let reopened = 0;
  let retained = 0;
  for (const customer of customerKeys) {
    if (reviewStage(events, customer) !== "closed") continue;
    const approval = events.findLast((event) => event.customer === customer && event.kind === "approved");
    if (!approval) continue;
    if (approval.snapshot === target) { retained++; continue; }
    const held = basisHolds(customer, approval.basis, target);
    if (held) retained++;
    else reopened++;
    const alreadyRecorded = events.some((event) => event.customer === customer && event.snapshot === target
      && (event.kind === "closure_retained" || event.kind === "reopened"));
    if (alreadyRecorded) continue;
    events.push({ customer, kind: held ? "closure_retained" : "reopened", snapshot: target, actor: engine, at,
      basis: approval.basis,
      rationale: held
        ? "The independent registry exclusion is still supported. The approved closure is retained."
        : "The verified DOB conflict cited in the approval is gone. V2 also supplies the documented Cantonese alias. Return to human review.",
      evidence: held ? approval.evidence : [...approval.evidence, fixtures.versions.V2.dobId,
        fixtures.versions.V2.alias.id, fixtures.customers.B.alias.id],
    });
  }
  return { state: { snapshot: target, events }, scanned: customerKeys.length, reopened, retained };
}

export function challengerHandoff(state: RescreenState) {
  const approval = state.events.findLast((event) => event.customer === "B" && event.kind === "approved");
  const reopening = state.events.findLast((event) => event.customer === "B" && event.kind === "reopened");
  if (!approval || !reopening) return null;
  return {
    case_id: fixtures.customers.B.id, synthetic: true, watchlist_entry_id: fixtures.watchlistEntryId,
    earlier_decision: { decision: "approved_false_positive", ...approval },
    changed_fields: { from: fixtures.versions.V1, to: fixtures.versions.V2 },
    customer: fixtures.customers.B, reopened: reopening,
  };
}
