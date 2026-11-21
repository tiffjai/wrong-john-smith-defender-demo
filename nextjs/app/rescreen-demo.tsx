"use client";

import { useState } from "react";
import { ArrowDownToLine, CircleCheck, GitCompare, ShieldAlert } from "lucide-react";
import fixtures from "../data/rescreen-fixtures.json";
import challengerReplay from "../data/recommendation_RESCREEN-B.json";
import { downloadJson } from "../lib/download-json";
import {
  analyst, auditReport, basisEvidence, challengerHandoff, compareFields, customerKeys, demoNotice,
  formatProbability, recordDecision, retrievalScore, reviewStage, romanisedName, senior, stageLabel,
  type Actor, type CustomerKey, type EvidenceMark, type RescreenState, type ReviewEvent, type Snapshot,
} from "../lib/rescreen";

const eventLabel: Record<ReviewEvent["kind"], string> = {
  proposed: "Closure proposed", approved: "False-positive closure approved", returned: "Returned to analyst",
  closure_retained: "Approved closure retained", reopened: "Reopened by rescreening", awaiting_evidence: "Evidence requested", escalated: "Escalated",
};
const defaultReason = {
  A: "Independent verified registry evidence identifies two separate people.",
  B: "The verified customer and watchlist dates of birth conflict in V1.",
};
const markClass: Record<EvidenceMark, string> = { supporting: "good", conflicting: "warn", missing: "quiet" };

export default function RescreenDemo({ state, onState, selected, onSelect }: {
  state: RescreenState; onState: (next: RescreenState) => void; selected: CustomerKey; onSelect: (customer: CustomerKey) => void;
}) {
  const [actor, setActor] = useState<Actor>(analyst);
  const [reason, setReason] = useState("");
  const [message, setMessage] = useState("");

  function decide(kind: Parameters<typeof recordDecision>[1]["kind"]) {
    try {
      const next = recordDecision(state, { customer: selected, kind, actor, rationale: reason, at: new Date().toISOString() });
      onState(next);
      setReason("");
      setMessage(`${eventLabel[kind]} for Customer ${selected}.`);
    } catch (error) { setMessage(error instanceof Error ? error.message : "The decision could not be saved."); }
  }

  const stage = reviewStage(state.events, selected);
  const customer = fixtures.customers[selected];
  const history = state.events.filter((event) => event.customer === selected);
  const approval = history.findLast((event) => event.kind === "approved");
  const handoff = challengerHandoff(state);
  const canPropose = actor.role === "analyst" && ["candidate", "returned"].includes(stage);
  const canApprove = actor.role === "senior" && stage === "pending";
  const canFollowUp = actor.role === "analyst" && ["reopened", "awaiting_evidence", "escalated"].includes(stage);
  const snapshots: Snapshot[] = state.loaded === "V2" ? ["V1", "V2"] : ["V1"];

  return <>
    <p className="demo-banner">{demoNotice}</p>
    <section className="panel rescreen-controls">
      <div><h2>Case review</h2><p>{fixtures.watchlistName} · <code>{fixtures.watchlistEntryId}</code></p>
        <small>Load V2 and Rescreen are on Watchlists. Loading a snapshot does not rescreen these cases.</small></div>
      <div className="version-pills">
        <div className="version-pill"><span>Loaded version</span><strong>{state.loaded}</strong></div>
        <div className="version-pill"><span>Screened version</span><strong>{state.snapshot}</strong></div>
      </div>
      <label>Active demo user<select value={actor.id} onChange={(event) => {
        setActor(event.target.value === analyst.id ? analyst : senior); setReason(""); setMessage("");
      }}><option value={analyst.id}>{analyst.name}</option><option value={senior.id}>{senior.name}</option></select></label>
      <button className="quiet-button" type="button" onClick={() => downloadJson("rescreen-audit.json", auditReport(state))}><ArrowDownToLine size={17}/>Download audit report</button>
      {state.loaded !== state.snapshot && <p className="muted rescreen-help">V2 is loaded and has not been screened. Case status still reflects {state.snapshot}.</p>}
      {message && <p className="inline-message rescreen-help" role="status">{message}</p>}
    </section>

    <div className="case-grid rescreen-grid">
      <section className="panel queue-panel">
        <div className="panel-title"><h2>Customer cases</h2><GitCompare size={18}/></div>
        <div className="queue-rows">{customerKeys.map((key) => {
          const outcome = reviewStage(state.events, key);
          return <button key={key} type="button" className={`case-row ${selected === key ? "selected" : ""}`}
            aria-pressed={selected === key} onClick={() => { onSelect(key); setReason(""); setMessage(""); }}>
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
        {selected === "A" && <div className="alias-banner"><CircleCheck size={20}/><div><strong>Independent registry exclusion</strong>
          <p>{fixtures.independentExclusion.value} <code>{fixtures.independentExclusion.id}</code> · {fixtures.independentExclusion.source}</p></div></div>}
        {selected === "B" && handoff && <div className="conflict-banner"><ShieldAlert size={20}/><div><strong>Earlier DOB conflict has been overturned</strong>
          <p>V2 corrects the watchlist DOB to {customer.dob} and adds the documented Cantonese alias. The original approval remains in history.</p></div></div>}
        <h3>Customer and watchlist evidence</h3>
        <p>Original V1 values stay visible. Supporting, conflicting and missing marks compare the customer record with each loaded snapshot.</p>
        <EvidenceComparison customer={selected} snapshots={snapshots} screened={state.snapshot}/>
        <h3>Retrieval and identity</h3>
        <p>Retrieval similarity uses normalised names and aliases. Identity probability is the Splink score and is not the retrieval threshold ({state.retrievalThreshold}).</p>
        <RetrievalTable customer={selected} snapshots={snapshots} state={state}/>
        {approval && <p className="finding"><strong>Original approval · {approval.snapshot}</strong> {approval.actor.name} ({approval.actor.id}) · {approval.rationale} <code>{approval.evidence.join(", ")}</code></p>}

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
          <button className="quiet-button" type="button" onClick={() => downloadJson("rescreen-b-challenger-packet.json", handoff)}>Export Challenger evidence</button></div>
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
  </>;
}

function EvidenceComparison({ customer, snapshots, screened }: { customer: CustomerKey; snapshots: Snapshot[]; screened: Snapshot }) {
  const fields = compareFields(customer, "V1");
  const compared = Object.fromEntries(snapshots.map((snapshot) => [snapshot, compareFields(customer, snapshot)])) as Record<Snapshot, ReturnType<typeof compareFields>>;
  return <div className="table-scroll"><table>
    <thead><tr><th>Field</th><th>Customer</th>{snapshots.map((snapshot) => <th key={snapshot}>Watchlist {snapshot}{snapshot === "V1" ? " · original" : " · loaded"}{snapshot === screened ? " · screened" : ""}</th>)}</tr></thead>
    <tbody>{fields.map((field, index) => <tr key={field.field}>
      <th scope="row">{field.label}</th>
      <td>{field.customer.value ?? "None"}{field.field === "name" && field.customer.value && <small className="review-timestamp">Normalised {romanisedName(field.customer.value)}</small>}
        {field.customer.evidenceId && <small className="review-timestamp"><code>{field.customer.evidenceId}</code> · {field.customer.snapshotId}</small>}
        <small className="review-timestamp">{field.customer.source}</small></td>
      {snapshots.map((snapshot) => {
        const cell = compared[snapshot][index];
        return <td key={snapshot}>{cell.watchlist.value ?? (cell.field === "registry" ? "Not a watchlist field" : "None")}
          {cell.field === "name" && cell.watchlist.value && <small className="review-timestamp">Normalised {romanisedName(cell.watchlist.value)}</small>}
          {cell.watchlist.evidenceId && <small className="review-timestamp"><code>{cell.watchlist.evidenceId}</code> · snapshot {cell.watchlist.snapshotId}</small>}
          <small className="review-timestamp">{cell.watchlist.source}</small>
          <span className={`status ${markClass[cell.mark]}`}>{cell.mark === "supporting" ? "Supporting" : cell.mark === "conflicting" ? "Conflicting" : "Missing"}</span>
        </td>;
      })}
    </tr>)}</tbody>
  </table></div>;
}

function RetrievalTable({ customer, snapshots, state }: { customer: CustomerKey; snapshots: Snapshot[]; state: RescreenState }) {
  return <div className="table-scroll"><table>
    <thead><tr><th>Snapshot</th><th>Retrieval similarity</th><th>Retrieved</th><th>Identity probability</th></tr></thead>
    <tbody>{snapshots.map((snapshot) => {
      const score = retrievalScore(customer, snapshot, state.retrievalThreshold);
      return <tr key={snapshot}>
        <th scope="row">{snapshot}{snapshot === state.snapshot ? " · screened" : snapshot === "V1" ? " · original" : " · loaded, not screened"}</th>
        <td>{score.retrievalSimilarity.toFixed(2)} <small>{score.retrievalSimilarityLabel}</small></td>
        <td><span className={`status ${score.retrieved ? "good" : "quiet"}`}>{score.retrieved ? "Retrieved" : "Not retrieved"}</span></td>
        <td>{formatProbability(score.identityProbability)} <small>{score.identityProbabilityLabel}</small></td>
      </tr>;
    })}</tbody>
  </table></div>;
}
