import fixtures from "../data/rescreen-fixtures.json";
import scores from "../data/rescreen-scores.json";

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
export type RescreenState = {
  /** Version whose screening result is currently applied to the two enrolled customers. */
  snapshot: Snapshot;
  /** Version loaded for inspection. Loading this does not screen. */
  loaded: Snapshot;
  /** Fuzzy name/alias cutoff, 0–100. This is not an identity probability. */
  retrievalThreshold: number;
  events: ReviewEvent[];
};
export type EvidenceMark = "supporting" | "conflicting" | "missing";
export type EvidenceCell = {
  value: string | null;
  evidenceId: string | null;
  source: string;
  snapshotId: string | null;
};
export type FieldComparison = {
  field: "name" | "alias" | "dob" | "registry";
  label: string;
  mark: EvidenceMark;
  customer: EvidenceCell;
  watchlist: EvidenceCell;
};
export type RetrievalScore = {
  customer: CustomerKey;
  snapshot: Snapshot;
  retrievalSimilarity: number;
  retrievalSimilarityLabel: "Retrieval similarity";
  identityProbability: number | null;
  identityProbabilityLabel: "Identity probability";
  retrieved: boolean;
  threshold: number;
  customerForm: string;
  watchlistForm: string;
  customerEvidenceId: string;
  watchlistEvidenceId: string;
};

export const rescreenStorageKey = "defender-rescreen-demo-v1";
export const DEFAULT_RETRIEVAL_THRESHOLD = 90;
export const demoNotice = "Synthetic browser-local demo. Two enrolled customers. Manual rescreen. No connected official feed and no automatic bank-wide screening. Decisions stay in this browser and are not stored in Supabase.";
export const initialRescreenState: RescreenState = {
  snapshot: "V1", loaded: "V1", retrievalThreshold: DEFAULT_RETRIEVAL_THRESHOLD, events: [],
};
export const customerKeys = ["A", "B"] as const;
export const analyst: Actor = { id: "DEMO-ANALYST-1", name: "Demo analyst", role: "analyst" };
export const senior: Actor = { id: "DEMO-REVIEWER-2", name: "Demo senior reviewer", role: "senior" };
const engine: Actor = { id: "DEMO-SYSTEM", name: "Rescreening engine", role: "system" };
export const stageLabel: Record<Stage, string> = {
  candidate: "Candidate", pending: "Pending senior approval", returned: "Returned to analyst",
  closed: "Closed · Approved false positive", reopened: "Reopened · Human review",
  awaiting_evidence: "Awaiting evidence", escalated: "Escalated",
};

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

export function normaliseThreshold(value: unknown) {
  const number = typeof value === "number" ? value : DEFAULT_RETRIEVAL_THRESHOLD;
  if (!Number.isFinite(number)) return DEFAULT_RETRIEVAL_THRESHOLD;
  return Math.min(100, Math.max(0, number));
}

export function readRescreenState(raw: string | null): RescreenState {
  try {
    const saved = JSON.parse(raw ?? "null") as Partial<RescreenState> | null;
    if (!saved || (saved.snapshot !== "V1" && saved.snapshot !== "V2") || !Array.isArray(saved.events)) return initialRescreenState;
    return {
      snapshot: saved.snapshot,
      loaded: saved.loaded === "V1" || saved.loaded === "V2" ? saved.loaded : saved.snapshot,
      retrievalThreshold: normaliseThreshold(saved.retrievalThreshold),
      events: saved.events as ReviewEvent[],
    };
  } catch {
    return initialRescreenState;
  }
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

export function loadWatchlist(state: RescreenState, version: Snapshot): { state: RescreenState; result: "ACTIVATED" | "NO_UPDATE" } {
  if (version === "V1" && state.loaded === "V2") throw new Error("V2 is already loaded. This demo does not roll the loaded snapshot back.");
  if (state.loaded === version) return { state, result: "NO_UPDATE" };
  return { state: { ...state, loaded: version }, result: "ACTIVATED" };
}

export function setRetrievalThreshold(state: RescreenState, value: number): RescreenState {
  return { ...state, retrievalThreshold: normaliseThreshold(value) };
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
  return {
    state: { ...state, snapshot: target, events },
    scanned: customerKeys.length, reopened, retained,
  };
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

export function normaliseName(value: string) {
  return value.normalize("NFKC").toLowerCase().replace(/[^\p{L}\p{N}\s]+/gu, " ").replace(/\s+/g, " ").trim();
}

export function romanisedName(value: string) {
  const parts = value.split(" / ");
  return normaliseName(parts[parts.length - 1] ?? value);
}

function indel(left: string, right: string) {
  const rows = left.length + 1;
  const cols = right.length + 1;
  const dp = Array.from({ length: rows }, () => new Array<number>(cols).fill(0));
  for (let i = 0; i < rows; i++) dp[i][0] = i;
  for (let j = 0; j < cols; j++) dp[0][j] = j;
  for (let i = 1; i < rows; i++) {
    for (let j = 1; j < cols; j++) {
      dp[i][j] = left[i - 1] === right[j - 1] ? dp[i - 1][j - 1] : Math.min(dp[i - 1][j], dp[i][j - 1]) + 1;
    }
  }
  return dp[left.length][right.length];
}

/** RapidFuzz-style token sort ratio on the normalised form, 0–100. */
export function tokenSortRatio(left: string, right: string) {
  const sort = (value: string) => normaliseName(value).split(" ").filter(Boolean).sort().join(" ");
  const a = sort(left);
  const b = sort(right);
  if (!a && !b) return 100;
  if (!a || !b) return 0;
  const similarity = (1 - indel(a, b) / (a.length + b.length)) * 100;
  return Math.round(similarity * 10000) / 10000;
}

export function formatProbability(value: number | null) {
  return value == null ? "Not scored" : `${(value * 100).toFixed(value >= .99 ? 5 : 2)}%`;
}

type NameForm = { kind: "name" | "alias"; value: string; observed: string; evidenceId: string };

function customerForms(customer: CustomerKey): NameForm[] {
  const record = fixtures.customers[customer];
  const forms: NameForm[] = [{ kind: "name", value: romanisedName(record.name), observed: record.name, evidenceId: record.nameId }];
  if (record.alias) forms.push({ kind: "alias", value: normaliseName(record.alias.value), observed: record.alias.value, evidenceId: record.alias.id });
  return forms;
}

function watchlistForms(snapshot: Snapshot): NameForm[] {
  const version = fixtures.versions[snapshot];
  const forms: NameForm[] = [{ kind: "name", value: romanisedName(version.name), observed: version.name, evidenceId: version.nameId }];
  if (version.alias) forms.push({ kind: "alias", value: normaliseName(version.alias.value), observed: version.alias.value, evidenceId: version.alias.id });
  return forms;
}

export function retrievalScore(customer: CustomerKey, snapshot: Snapshot, threshold: number): RetrievalScore {
  const ranked = customerForms(customer).flatMap((customerForm) => watchlistForms(snapshot).map((watchlistForm) => ({
    customerForm, watchlistForm,
    score: tokenSortRatio(customerForm.value, watchlistForm.value),
    preference: (customerForm.kind === "alias" ? 2 : 0) + (watchlistForm.kind === "alias" ? 1 : 0),
  }))).sort((left, right) => right.score - left.score || right.preference - left.preference);
  const best = ranked[0];
  const cutoff = normaliseThreshold(threshold);
  return {
    customer, snapshot,
    retrievalSimilarity: best.score,
    retrievalSimilarityLabel: "Retrieval similarity",
    identityProbability: scores[snapshot][customer].splink,
    identityProbabilityLabel: "Identity probability",
    retrieved: best.score >= cutoff,
    threshold: cutoff,
    customerForm: best.customerForm.observed,
    watchlistForm: best.watchlistForm.observed,
    customerEvidenceId: best.customerForm.evidenceId,
    watchlistEvidenceId: best.watchlistForm.evidenceId,
  };
}

function evidenceCell(value: string | null, evidenceId: string | null, source: string, snapshotId: string | null): EvidenceCell {
  return { value, evidenceId, source, snapshotId };
}

export function compareFields(customer: CustomerKey, snapshot: Snapshot): FieldComparison[] {
  const record = fixtures.customers[customer];
  const version = fixtures.versions[snapshot];
  const listSource = `${fixtures.watchlistSource} · ${snapshot} · published ${version.published}`;
  const customerName = romanisedName(record.name);
  const listName = romanisedName(version.name);
  const customerAlias = record.alias?.value ?? null;
  const listAlias = version.alias?.value ?? null;
  const rows: FieldComparison[] = [
    {
      field: "name", label: "Name",
      mark: customerName && listName ? (customerName === listName ? "supporting" : "conflicting") : "missing",
      customer: evidenceCell(record.name, record.nameId, record.source, "KYC"),
      watchlist: evidenceCell(version.name, version.nameId, listSource, snapshot),
    },
    {
      field: "alias", label: "Documented alias",
      mark: customerAlias && listAlias ? (normaliseName(customerAlias) === normaliseName(listAlias) ? "supporting" : "conflicting") : "missing",
      customer: evidenceCell(customerAlias, record.alias?.id ?? null, record.alias?.source ?? record.source, "KYC"),
      watchlist: evidenceCell(listAlias, version.alias?.id ?? null, version.alias?.source ?? listSource, snapshot),
    },
    {
      field: "dob", label: "Date of birth",
      mark: record.dob && version.dob ? (record.dob === version.dob ? "supporting" : "conflicting") : "missing",
      customer: evidenceCell(record.dob, record.dobId, record.source, "KYC"),
      watchlist: evidenceCell(version.dob, version.dobId, listSource, snapshot),
    },
  ];
  if (customer === "A") {
    rows.push({
      field: "registry", label: "Independent registry exclusion", mark: "supporting",
      customer: evidenceCell(fixtures.independentExclusion.value, fixtures.independentExclusion.id, fixtures.independentExclusion.source, "KYC"),
      watchlist: evidenceCell(null, null, "Not a watchlist field. This exclusion is independent of the list snapshot.", snapshot),
    });
  }
  return rows;
}

export function auditReport(state: RescreenState) {
  const history = state.events;
  const identities = [...new Map(history.map((event) => [event.actor.id, event.actor])).values()];
  return {
    synthetic: true,
    persistence: "browser-local",
    supabasePersistence: false,
    officialFeedConnected: false,
    automaticBankWideScreening: false,
    manualRescreen: true,
    enrolledCustomers: customerKeys.map((customer) => fixtures.customers[customer].id),
    watchlistEntryId: fixtures.watchlistEntryId,
    loadedVersion: state.loaded,
    screenedVersion: state.snapshot,
    retrievalThreshold: state.retrievalThreshold,
    reviewerIdentities: identities,
    cases: customerKeys.map((customer) => {
      const events = history.filter((event) => event.customer === customer);
      return {
        caseId: fixtures.customers[customer].id,
        customer,
        stage: reviewStage(history, customer),
        basis: closureBasis(customer),
        evidence: { V1: compareFields(customer, "V1"), V2: compareFields(customer, "V2") },
        retrieval: {
          V1: retrievalScore(customer, "V1", state.retrievalThreshold),
          V2: retrievalScore(customer, "V2", state.retrievalThreshold),
        },
        decisions: events.filter((event) => event.kind === "proposed" || event.kind === "approved" || event.kind === "returned"),
        rescreenEvents: events.filter((event) => event.kind === "closure_retained" || event.kind === "reopened"),
        history: events,
      };
    }),
  };
}
