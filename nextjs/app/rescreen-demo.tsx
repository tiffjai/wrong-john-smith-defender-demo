"use client";

import { useEffect, useState } from "react";
import { CircleCheck, GitCompare, ShieldAlert } from "lucide-react";
import fixtures from "../data/rescreen-fixtures.json";
import scores from "../data/rescreen-scores.json";
import challengerReplay from "../data/recommendation_RESCREEN-B.json";
import {
  analyst, basisEvidence, challengerHandoff, customerKeys, initialRescreenState,
  recordDecision, rescreen, reviewStage, senior, type Actor, type CustomerKey,
  type RescreenState, type ReviewEvent, type Snapshot,
} from "../lib/rescreen";

const storageKey = "defender-rescreen-demo-v1";
const stageLabel = {
  candidate: "Candidate", pending: "Pending senior approval", returned: "Returned to analyst",
  closed: "Closed · Approved false positive", reopened: "Reopened · Human review",
  awaiting_evidence: "Awaiting evidence", escalated: "Escalated",
};
const eventLabel: Record<ReviewEvent["kind"], string> = {
  proposed: "Closure proposed", approved: "False-positive closure approved", returned: "Returned to analyst",
  closure_retained: "Approved closure retained", reopened: "Reopened by rescreening", awaiting_evidence: "Evidence requested", escalated: "Escalated",
};
const defaultReason = {
  A: "Independent verified registry evidence identifies two separate people.",
  B: "The verified customer and watchlist dates of birth conflict in V1.",
};

function readState(): RescreenState {
  try {
    const saved = JSON.parse(localStorage.getItem(storageKey) ?? "null");
    if (saved && ["V1", "V2"].includes(saved.snapshot) && Array.isArray(saved.events)) return saved as RescreenState;
  } catch { /* Start an empty rehearsal if storage is disabled. */ }
  return initialRescreenState;
}

function formatProbability(value: number | null) {
  return value == null ? "Not scored" : `${(value * 100).toFixed(value >= .99 ? 5 : 2)}%`;
}

function saveHandoff(packet: NonNullable<ReturnType<typeof challengerHandoff>>) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(packet, null, 2)], { type: "application/json" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = "rescreen-b-challenger-packet.json";
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export default function RescreenDemo() {
  const [state, setState] = useState(initialRescreenState);
  const [actor, setActor] = useState<Actor>(analyst);
  const [selected, setSelected] = useState<CustomerKey>("A");
  const [reason, setReason] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    setState(readState());
    const sync = (event: StorageEvent) => { if (event.key === storageKey) setState(readState()); };
    window.addEventListener("storage", sync);
    return () => window.removeEventListener("storage", sync);
  }, []);

  function persist(next: RescreenState) {
    localStorage.setItem(storageKey, JSON.stringify(next));
    setState(next);
  }

  function decide(kind: Parameters<typeof recordDecision>[1]["kind"]) {
    try {
      const next = recordDecision(readState(), { customer: selected, kind, actor, rationale: reason, at: new Date().toISOString() });
      persist(next);
      setReason("");
      setMessage(`${eventLabel[kind]} for Customer ${selected}.`);
    } catch (error) { setMessage(error instanceof Error ? error.message : "The decision could not be saved."); }
  }

  function run(target: Snapshot) {
    try {
      const result = rescreen(readState(), target, new Date().toISOString());
      persist(result.state);
      setMessage(`${target} checked ${result.scanned} customers. ${result.retained} approved closure${result.retained === 1 ? "" : "s"} retained. ${result.reopened} new reopening${result.reopened === 1 ? "" : "s"}.`);
      if (result.reopened) { setSelected("B"); setReason(""); }
    } catch (error) { setMessage(error instanceof Error ? error.message : "The rescreen could not be saved."); }
  }

  const stage = reviewStage(state.events, selected);
  const customer = fixtures.customers[selected];
  const history = state.events.filter((event) => event.customer === selected);
  const approval = history.findLast((event) => event.kind === "approved");
  const handoff = challengerHandoff(state);
  const bothApproved = customerKeys.every((key) => reviewStage(state.events, key) === "closed");
  const canPropose = actor.role === "analyst" && ["candidate", "returned"].includes(stage);
  const canApprove = actor.role === "senior" && stage === "pending";
  const canFollowUp = actor.role === "analyst" && ["reopened", "awaiting_evidence", "escalated"].includes(stage);

  return <>
    <section className="panel rescreen-controls">
      <div><h2>One watchlist update</h2><p>{fixtures.watchlistName} · <code>{fixtures.watchlistEntryId}</code> · Active snapshot <strong>{state.snapshot}</strong></p>
        <small>Rehearsal accounts simulate the analyst and senior reviewer roles on this browser.</small></div>
      <label>Active demo user<select value={actor.id} onChange={(event) => {
        setActor(event.target.value === analyst.id ? analyst : senior); setReason(""); setMessage("");
      }}><option value={analyst.id}>{analyst.name}</option><option value={senior.id}>{senior.name}</option></select></label>
      <div className="rescreen-actions"><button className="primary" disabled={state.snapshot === "V1" && !bothApproved} onClick={() => run("V2")}>Load V2 and Rescreen</button>
        <button className="quiet-button" onClick={() => run(state.snapshot)}>Run daily sweep</button></div>
      {state.snapshot === "V1" && !bothApproved && <p className="muted rescreen-help">Approve both V1 closures to run the V2 comparison.</p>}
      {message && <p className="inline-message rescreen-help" role="status">{message}</p>}
    </section>

    <div className="case-grid rescreen-grid">
      <section className="panel queue-panel">
        <div className="panel-title"><h2>Customer cases</h2><GitCompare size={18}/></div>
        <div className="queue-rows">{customerKeys.map((key) => {
          const outcome = reviewStage(state.events, key);
          return <button key={key} type="button" className={`case-row ${selected === key ? "selected" : ""}`}
            aria-pressed={selected === key} onClick={() => { setSelected(key); setReason(""); setMessage(""); }}>
            <small>{fixtures.customers[key].id}</small><strong>Customer {key}</strong>
            <span className={`status ${outcome === "closed" ? "good" : "warn"}`}>{stageLabel[outcome]}</span>
          </button>;
        })}</div>
      </section>
      <section className="panel detail-panel">
        <div className="case-top"><div><p className="case-ref">{customer.id}</p><h2>Customer {selected}</h2>
          <p>{customer.name} · {customer.dob}</p><small>{customer.precision} · <code>{customer.nameId}, {customer.dobId}</code> · {customer.source}</small>
        </div><span className={`status ${stage === "closed" ? "good" : "warn"}`}>{stageLabel[stage]}</span></div>
        {customer.alias && <p className="finding"><strong>Documented customer alias</strong> {customer.alias.value} · <code>{customer.alias.id}</code> · {customer.alias.source}</p>}
        {selected === "A" && <div className="alias-banner"><CircleCheck size={20}/><div><strong>Independent exclusion</strong>
          <p>{fixtures.independentExclusion.value} <code>{fixtures.independentExclusion.id}</code> · {fixtures.independentExclusion.source}</p></div></div>}
        {selected === "B" && handoff && <div className="conflict-banner"><ShieldAlert size={20}/><div><strong>Earlier DOB conflict has been overturned</strong>
          <p>V2 corrects the watchlist DOB to {customer.dob} and adds the documented Cantonese alias. The original approval remains in history.</p></div></div>}
        <h3>Match and source evidence</h3>
        <EvidenceComparison customer={selected} active={state.snapshot}/>
        {approval && <p className="finding"><strong>Original approval · {approval.snapshot}</strong> {approval.actor.name} · {approval.rationale} <code>{approval.evidence.join(", ")}</code></p>}

        {stage === "pending" && actor.role === "analyst" && <p className="finding">Waiting for a different senior reviewer. The proposing analyst cannot approve their own closure.</p>}
        {(canPropose || canApprove || canFollowUp) && <section className="review-form">
          <h3>{canPropose ? "Propose false-positive closure" : canApprove ? "Review closure proposal" : "Respond to reopened case"}</h3>
          {canPropose && <p>{defaultReason[selected]} <code>{basisEvidence(selected, state.snapshot).join(", ")}</code></p>}
          <label>Rationale<textarea value={reason} onChange={(event) => setReason(event.target.value)} maxLength={1000} rows={2}/></label>
          <div className="rescreen-actions">
            {canPropose && <button className="primary" disabled={!reason.trim()} onClick={() => decide("proposed")}>Submit closure proposal</button>}
            {canApprove && <><button className="primary" disabled={!reason.trim()} onClick={() => decide("approved")}>Approve false-positive closure</button>
              <button className="quiet-button" disabled={!reason.trim()} onClick={() => decide("returned")}>Return to analyst</button></>}
            {canFollowUp && <><button className="primary" disabled={!reason.trim()} onClick={() => decide("awaiting_evidence")}>Request evidence</button>
              <button className="quiet-button" disabled={!reason.trim()} onClick={() => decide("escalated")}>Escalate reopened case</button></>}
          </div>
        </section>}

        {selected === "B" && handoff && <section className="grok-card"><div className="panel-title"><h3>DefenderChallenger handoff</h3>
          <button className="quiet-button" onClick={() => saveHandoff(handoff)}>Export Challenger evidence</button></div>
          <p>Includes both snapshot references, the previous approval, and the reopening evidence IDs. The analyst controls disposition.</p>
          <details><summary>Saved Grok review from the QA rehearsal</summary>
            {challengerReplay.contradictions.map(({ finding, evidence_ids }) => <p key={finding}>
              {finding} <code>{evidence_ids.join(", ")}</code>
            </p>)}
            <p><strong>Next check</strong> {challengerReplay.suggested_next_check}</p>
          </details>
        </section>}

        {history.length > 0 && <section className="history" aria-label={`Customer ${selected} review history`}><h3>Review and rescreen history</h3>
          {history.map((event, index) => <article key={`${event.at}-${event.kind}-${index}`}>
            <strong>{eventLabel[event.kind]}</strong><small> · {event.snapshot} · {event.actor.name} ({event.actor.id})</small>
            <time dateTime={event.at}>{new Date(event.at).toLocaleString("en-GB", { timeZone: "Europe/London" })}</time>
            <p>{event.rationale}</p><small>Evidence <code>{event.evidence.join(", ")}</code></small>
          </article>)}
        </section>}
      </section>
    </div>
    {state.snapshot === "V2" && <ThresholdReplay/>}
  </>;
}

function EvidenceComparison({ customer, active }: { customer: CustomerKey; active: Snapshot }) {
  const snapshots: Snapshot[] = active === "V2" ? ["V1", "V2"] : ["V1"];
  const record = fixtures.customers[customer];
  const labels = {
    name: "Original watchlist name", source: "Snapshot and source", alias: "Cantonese alias", dob: "Watchlist DOB",
  };
  return <>
    <div className="table-scroll"><table><thead><tr><th>Field</th>{snapshots.map((version) => <th key={version}>{version}</th>)}</tr></thead>
      <tbody>
        <tr><th scope="row">{labels.source}</th>{snapshots.map((version) => <td key={version}>{fixtures.versions[version].published}<small className="review-timestamp">{fixtures.watchlistSource}</small></td>)}</tr>
        <tr><th scope="row">{labels.name}</th>{snapshots.map((version) => <td key={version}>{fixtures.versions[version].name} <code>{fixtures.versions[version].nameId}</code></td>)}</tr>
        <tr><th scope="row">{labels.alias}</th>{snapshots.map((version) => {
          const alias = fixtures.versions[version].alias;
          return <td key={version}>{alias ? <>{alias.value} <code>{alias.id}</code><small className="review-timestamp">{alias.source}</small>
            {record.alias?.value === alias.value && <span className="status good">Supporting evidence</span>}</> : <span className="status quiet">Missing</span>}</td>;
        })}</tr>
        <tr><th scope="row">{labels.dob}</th>{snapshots.map((version) => {
          const evidence = fixtures.versions[version];
          const match = record.dob === evidence.dob;
          return <td key={version}>{evidence.dob} <code>{evidence.dobId}</code><small className="review-timestamp">{evidence.precision}</small>
            <span className={`status ${match ? "good" : "warn"}`}>{match ? "Supporting" : "Conflicting"}</span></td>;
        })}</tr>
        <tr><th scope="row">RapidFuzz name only</th>{snapshots.map((version) => <td key={version}>{scores[version][customer].rapidfuzz.toFixed(2)} / 100</td>)}</tr>
        <tr><th scope="row">Splink · DuckDB</th>{snapshots.map((version) => <td key={version}>{formatProbability(scores[version][customer].splink)}</td>)}</tr>
      </tbody></table></div>
    <details className="evidence-details"><summary>Jurisdiction source coverage</summary>
      <p>UK: one fictional feed checked under {active}. US and Mainland China: no source checked in this exercise. A reviewer records applicability after obtaining jurisdiction-specific evidence.</p>
    </details>
  </>;
}

function ThresholdReplay() {
  const [result, setResult] = useState(false);
  const watchlistCandidate = scores.V2.B;
  const baseline = 0.8;
  const proposed = 0.99995;
  const qualifies = watchlistCandidate.splink != null && watchlistCandidate.splink >= proposed;
  return <section className="panel feed-panel rescreen-controls">
    <div><h2>QA threshold replay</h2><p>Replay the labelled V2 true pair RESCREEN-B under a proposed 99.995% Splink threshold.</p></div>
    <button className="quiet-button" onClick={() => setResult(true)}>Replay proposed threshold</button>
    {result && <p role="status" className="rescreen-help">Candidate retrieval: {watchlistCandidate.retrieved ? "retained" : "missed"}.
      {" "}Splink score: {formatProbability(watchlistCandidate.splink)}. Baseline threshold: {baseline * 100}%.
      {" "}{!watchlistCandidate.retrieved ? "Lost at candidate retrieval." : qualifies ? "Proposed threshold retains the pair." : "Lost at scoring. Hold this threshold change for review."}</p>}
  </section>;
}
