"use client";

import { useState } from "react";
import { ArrowDownToLine, Library } from "lucide-react";
import fixtures from "../data/rescreen-fixtures.json";
import { downloadJson } from "../lib/download-json";
import {
  auditReport, customerKeys, demoNotice, formatProbability, loadWatchlist, rescreen,
  retrievalScore, reviewStage, setRetrievalThreshold, stageLabel, type CustomerKey,
  type RescreenState, type Snapshot,
} from "../lib/rescreen";

export default function WatchlistsPanel({ state, onState }: { state: RescreenState; onState: (next: RescreenState) => void }) {
  const [message, setMessage] = useState("");
  const report = auditReport(state);
  const visibleSnapshots: Snapshot[] = state.loaded === "V2" ? ["V1", "V2"] : ["V1"];
  const bothClosed = customerKeys.every((customer) => reviewStage(state.events, customer) === "closed");

  function load() {
    try {
      const result = loadWatchlist(state, "V2");
      onState(result.state);
      setMessage(result.result === "NO_UPDATE"
        ? `V2 is already loaded. Screened version remains ${state.snapshot}. No rescreen was run.`
        : `V2 loaded. Screened version remains ${result.state.snapshot}. Rescreen has not run.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "The snapshot could not be loaded.");
    }
  }

  function run() {
    try {
      const result = rescreen(state, state.loaded, new Date().toISOString());
      onState(result.state);
      setMessage(`Manual rescreen against ${state.loaded}. Screened version is now ${result.state.snapshot}. ${result.reopened} new reopening${result.reopened === 1 ? "" : "s"}. ${result.retained} approved closure${result.retained === 1 ? "" : "s"} retained.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "The rescreen could not be saved.");
    }
  }

  return <div>
    <p className="demo-banner">{demoNotice}</p>
    <section className="panel rescreen-controls">
      <div>
        <div className="panel-title"><h2>DEMO-WL-410</h2><Library size={18}/></div>
        <p>{fixtures.watchlistName} · <code>{fixtures.watchlistEntryId}</code></p>
        <small>Two enrolled customers, {fixtures.customers.A.id} and {fixtures.customers.B.id}. Load and rescreen are separate manual steps.</small>
      </div>
      <div className="version-pills" aria-label="Watchlist versions">
        <div className="version-pill"><span>Loaded version</span><strong>{state.loaded}</strong></div>
        <div className="version-pill"><span>Screened version</span><strong>{state.snapshot}</strong></div>
      </div>
      <div className="rescreen-actions">
        <button className="primary" type="button" onClick={load}>Load V2</button>
        <button className="quiet-button" type="button" onClick={run}>Rescreen</button>
      </div>
      {state.loaded === "V2" && state.snapshot === "V1" && !bothClosed && <p className="muted rescreen-help">Approve both closures on V2 rescreen demo before rescreening onto V2. Load V2 does not change the screened version.</p>}
      {state.loaded === "V1" && <p className="muted rescreen-help">Load V2 to bring in the corrected snapshot. Screening stays on V1 until you press Rescreen.</p>}
      {message && <p className="inline-message rescreen-help" role="status">{message}</p>}
    </section>

    <section className="panel feed-panel">
      <div className="panel-title"><h2>Enrolled customers</h2></div>
      <ul>{customerKeys.map((customer) => <li key={customer}>{fixtures.customers[customer].id}: {stageLabel[reviewStage(state.events, customer)]}</li>)}</ul>
      <p data-testid="reopen-count">Reopen events: {state.events.filter((event) => event.kind === "reopened").length}</p>
    </section>

    <section className="panel feed-panel">
      <div className="panel-title"><h2>Candidate retrieval</h2></div>
      <p>Retrieval similarity is the best fuzzy score over normalised names and aliases. Identity probability is the separate Splink score. The threshold applies only to retrieval.</p>
      <div className="threshold-control">
        <label htmlFor="retrieval-threshold">Retrieval threshold</label>
        <input id="retrieval-threshold" type="range" min={0} max={100} step={1} value={state.retrievalThreshold}
          onChange={(event) => onState(setRetrievalThreshold(state, Number(event.target.value)))}/>
        <span>{state.retrievalThreshold} out of 100</span>
      </div>
      <div className="table-scroll"><table>
        <caption>Retrieved candidates for loaded snapshots</caption>
        <thead><tr><th>Customer</th><th>Snapshot</th><th>Retrieval similarity</th><th>Retrieved</th><th>Identity probability</th><th>Best normalised match</th></tr></thead>
        <tbody>{visibleSnapshots.flatMap((snapshot) => customerKeys.map((customer) => {
          const score = retrievalScore(customer, snapshot, state.retrievalThreshold);
          return <tr key={`${customer}-${snapshot}`}>
            <th scope="row">{fixtures.customers[customer].id}</th>
            <td>{snapshot}{snapshot === state.snapshot ? " · screened" : snapshot === state.loaded ? " · loaded, not screened" : " · original"}</td>
            <td>{score.retrievalSimilarity.toFixed(2)}</td>
            <td><span className={`status ${score.retrieved ? "good" : "quiet"}`}>{score.retrieved ? "Retrieved" : "Not retrieved"}</span></td>
            <td>{formatProbability(score.identityProbability)}</td>
            <td>{score.customerForm} ↔ {score.watchlistForm}<small className="review-timestamp"><code>{score.customerEvidenceId}</code> · <code>{score.watchlistEvidenceId}</code></small></td>
          </tr>;
        }))}</tbody>
      </table></div>
    </section>

    <section className="panel feed-panel audit-block" aria-label="Audit report" id="audit-report">
      <div className="panel-title"><h2>Audit report</h2>
        <button className="quiet-button" type="button" onClick={() => downloadJson("rescreen-audit.json", report)}><ArrowDownToLine size={17}/>Download audit report</button>
      </div>
      <p>Both enrolled cases, with V1 and V2 evidence, decisions, reviewer identities, reasons and rescreen events. Loaded version {report.loadedVersion}. Screened version {report.screenedVersion}.</p>
      {report.cases.map((entry) => <article className="audit-case" key={entry.caseId}>
        <h3>{entry.caseId} · {stageLabel[entry.stage]}</h3>
        <p>Basis <code>{entry.basis}</code></p>
        <p><strong>Analyst recommendation</strong> {decisionText(entry.decisions, "proposed")}</p>
        <p><strong>Senior approval</strong> {decisionText(entry.decisions, "approved")}</p>
        <p><strong>V1 evidence</strong> <code>{evidenceIds(entry.evidence.V1).join(", ") || "None"}</code></p>
        <p><strong>V2 evidence</strong> <code>{evidenceIds(entry.evidence.V2).join(", ") || "None"}</code></p>
        <p><strong>Rescreen events</strong> {entry.rescreenEvents.length ? entry.rescreenEvents.map((event) => `${event.kind} · ${event.snapshot} · ${event.actor.name} (${event.actor.id}): ${event.rationale}`).join(" ") : "None yet"}</p>
      </article>)}
    </section>
  </div>;
}

function decisionText(events: RescreenState["events"], kind: "proposed" | "approved") {
  const event = events.findLast((item) => item.kind === kind);
  if (!event) return kind === "approved" ? "Awaiting a different senior reviewer." : "None yet.";
  return `${event.actor.name} (${event.actor.id}) · ${event.rationale} · evidence ${event.evidence.join(", ")}`;
}

function evidenceIds(rows: { customer: { evidenceId: string | null }; watchlist: { evidenceId: string | null } }[]) {
  return [...new Set(rows.flatMap((row) => [row.customer.evidenceId, row.watchlist.evidenceId].filter((id): id is string => Boolean(id))))];
}

export function RescreenReviews({ state, onOpen }: { state: RescreenState; onOpen: (customer: CustomerKey) => void }) {
  const report = auditReport(state);
  return <section className="panel review-queue">
    <p className="demo-banner">{demoNotice}</p>
    <div className="panel-title"><h2>Rescreen closures</h2></div>
    <p>Analyst recommendations stay distinct from senior approvals. This history is the same browser-local rehearsal as Watchlists.</p>
    <div className="table-scroll"><table>
      <thead><tr><th>Case</th><th>Stage</th><th>Analyst recommendation</th><th>Senior approval</th><th>Evidence</th><th>Rescreen</th><th>Action</th></tr></thead>
      <tbody>{report.cases.map((entry) => <tr key={entry.caseId}>
        <td><strong>{entry.caseId}</strong><small>{fixtures.watchlistEntryId}</small></td>
        <td><span className={`status ${entry.stage === "closed" ? "good" : "warn"}`}>{stageLabel[entry.stage]}</span></td>
        <td>{decisionText(entry.decisions, "proposed")}</td>
        <td>{decisionText(entry.decisions, "approved")}</td>
        <td className="evidence-ids">{evidenceIds([...entry.evidence.V1, ...entry.evidence.V2]).map((id) => <code key={id}>{id}</code>)}</td>
        <td>{entry.rescreenEvents.map((event) => `${event.kind} (${event.actor.name})`).join(", ") || "Not rescreened"}</td>
        <td><button className="quiet-button" type="button" onClick={() => onOpen(entry.customer)}>Open case</button></td>
      </tr>)}</tbody>
    </table></div>
  </section>;
}
