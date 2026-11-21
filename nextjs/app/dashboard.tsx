"use client";

import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import {
  Activity, ArrowDownToLine, ChartNoAxesCombined, CircleHelp, Database, FileSearch,
  ClipboardCheck, Fingerprint, Layers3, Library, ListFilter, LogOut, Search, ShieldAlert, ShieldCheck,
} from "lucide-react";
import { signOut } from "./login/actions";
import type { Benchmark, Case, DashboardMode, Decision, Review } from "../lib/types";
import { initialRescreenState, readRescreenState, rescreenStorageKey, type CustomerKey, type RescreenState } from "../lib/rescreen";
import { DocumentEvidence, OwnershipEvidence } from "./case-evidence";
import SanctionsDetail from "./sanctions-detail";
import RescreenDemo from "./rescreen-demo";
import WatchlistsPanel, { RescreenReviews } from "./watchlists";

const modes = [
  { id: "queue", label: "Screening queue", icon: FileSearch },
  { id: "reviews", label: "Reviews", icon: ClipboardCheck },
  { id: "watchlists", label: "Watchlists", icon: Library },
  { id: "rescreen", label: "V2 rescreen demo", icon: Activity },
  { id: "benchmark", label: "Matching benchmark", icon: ChartNoAxesCombined },
  { id: "feeds", label: "Data sources", icon: Database },
] as const;
type View = typeof modes[number]["id"];

const decisionLabels: Record<Decision, string> = {
  awaiting_evidence: "Awaiting evidence", escalated_sanctions: "Escalated to Sanctions",
  escalated_legal: "Escalated to Legal", resolved: "Resolved",
};
const matchLabels: Record<string, string> = {
  LINK: "Link", REVIEW: "Review", NO_LINK: "No link", NOT_SCORED: "Unscored",
  ANALYST_REVIEW: "Analyst review", CANDIDATE_VISIBLE: "Candidate visible", NO_CANDIDATE: "No candidate",
};

function Status({ value }: { value: string }) {
  const kind = value.includes("REVIEW") ? "warn" : ["LINK", "CANDIDATE_VISIBLE"].includes(value) ? "good" : "quiet";
  return <span className={`status ${kind}`}>{matchLabels[value] ?? value}</span>;
}

function Metric({ icon, label, value, detail }: { icon: ReactNode; label: string; value: string | number; detail: string }) {
  return <div className="metric"><div className="metric-icon">{icon}</div><div>
    <p>{label}</p><strong>{value}</strong><small>{detail}</small>
  </div></div>;
}

function displayNumber(n: number) { return n.toLocaleString("en-GB"); }
function percent(n: number) { return `${(n * 100).toFixed(1)}%`; }

function downloadPacket(selected: Case) {
  const blob = new Blob([JSON.stringify(selected.packet, null, 2) + "\n"], { type: "application/json" });
  const href = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = href;
  anchor.download = `${selected.id.toLowerCase()}-evidence.json`;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(href), 1000);
}

export default function Dashboard({ mode, cases, benchmark, reviews, profile }: {
  mode: DashboardMode; cases: Case[]; benchmark: Benchmark; reviews: Review[];
  profile?: { booking_entity: string; review_role: string };
}) {
  const [view, setView] = useState<View>("queue");
  const [selectedId, setSelectedId] = useState(cases[0]?.id);
  const [history, setHistory] = useState(reviews);
  const [v2, setV2] = useState(false);
  const [feedMessage, setFeedMessage] = useState("");
  const [filter, setFilter] = useState("");
  const [rescreenState, setRescreenState] = useState(initialRescreenState);
  const [rescreenCustomer, setRescreenCustomer] = useState<CustomerKey>("A");

  useEffect(() => {
    if (mode !== "demo") return;
    try {
      const cached = JSON.parse(localStorage.getItem("defender-review-events") ?? "[]");
      if (Array.isArray(cached)) setHistory(cached);
      setV2(localStorage.getItem("defender-fixture-v2") === "loaded");
    } catch { /* The offline demo remains usable with a fresh history. */ }
  }, [mode]);

  useEffect(() => {
    if (mode !== "demo") return;
    setRescreenState(readRescreenState(localStorage.getItem(rescreenStorageKey)));
    const sync = (event: StorageEvent) => {
      if (event.key === rescreenStorageKey) setRescreenState(readRescreenState(event.newValue));
    };
    window.addEventListener("storage", sync);
    return () => window.removeEventListener("storage", sync);
  }, [mode]);

  function commitRescreen(next: RescreenState) {
    try { localStorage.setItem(rescreenStorageKey, JSON.stringify(next)); } catch { /* Keep the in-memory rehearsal if storage is blocked. */ }
    setRescreenState(next);
  }

  function loadV2() {
    if (v2) {
      setFeedMessage("V2 is already active. No duplicate alert was added.");
      return;
    }
    setV2(true);
    try { localStorage.setItem("defender-fixture-v2", "loaded"); } catch { /* Session-only replay. */ }
    setFeedMessage("V2 activated. The documented alias surfaced CASE-03.");
  }

  async function saveReview(caseId: string, decision: Decision, rationale: string) {
    if (mode === "supabase") {
      const response = await fetch("/api/reviews", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ case_id: caseId, decision, rationale }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.error ?? "Could not save this review.");
      setHistory((events) => [body as Review, ...events]);
    } else {
      const entry = { case_id: caseId, decision, rationale, created_at: new Date().toISOString() };
      const next = [entry, ...history];
      localStorage.setItem("defender-review-events", JSON.stringify(next));
      setHistory(next);
    }
  }

  const modeCases = mode === "demo" && !v2 ? cases.filter((entry) => entry.snapshot === "V1") : cases;
  const selected = modeCases.find((entry) => entry.id === selectedId) ?? modeCases[0];
  const rows = modeCases.filter((entry) => `${entry.id} ${entry.title} ${entry.booking_entity}`.toLowerCase().includes(filter.trim().toLowerCase()));
  const conflicts = modeCases.filter((entry) => entry.packet.case_outcome.splink_with_guard === "ANALYST_REVIEW").length;
  const subtitle = view === "queue" ? "Compare match evidence and document the analyst decision."
    : view === "reviews" ? "Track cases before and after a human decision."
    : view === "watchlists" ? "Load a snapshot, then manually rescreen the two enrolled customers."
    : view === "rescreen" ? "Propose and approve the two V1 closures. Load and rescreen from Watchlists."
    : view === "benchmark" ? "Compare two matchers on the same FEBRL4 candidate pairs."
    : "Inspect the demo snapshots and the benchmark’s provenance.";

  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><div className="brand-emblem"><Fingerprint size={23} /></div>
        <div>Defender<small>Identity screening</small></div></div>
      <nav aria-label="Workspace">
        {modes.filter(({ id }) => mode === "demo" || (id !== "rescreen" && id !== "watchlists")).map(({ id, label, icon: Icon }) => <button key={id} type="button" onClick={() => setView(id)}
          className={id === view ? "nav-button active" : "nav-button"} aria-current={id === view ? "page" : undefined}>
          <Icon size={18}/><span>{label}</span>
        </button>)}
      </nav>
      <div className="sidebar-bottom">
        <div className="workspace-tag"><Activity size={16}/>{mode === "demo" ? "Offline demo" : "Supabase connected"}</div>
        <div className="workspace-caption">{profile ? `${profile.booking_entity} · ${profile.review_role}` : "Synthetic records"}</div>
        {mode === "supabase" && <form action={signOut}><button className="signout"><LogOut size={16}/>Sign out</button></form>}
      </div>
    </aside>

    <main className="workspace">
      <header className="workspace-header"><div>
        <h1>{modes.find((entry) => entry.id === view)?.label}</h1><p>{subtitle}</p>
      </div><span className="synthetic-tag"><ShieldCheck size={16}/>Synthetic data</span></header>

      {view === "queue" && <>
        <section className="metrics" aria-label="Screening and benchmark summary">
          <Metric icon={<Layers3 size={21}/>} label="Visible cases" value={modeCases.length} detail={mode === "demo" ? `Snapshot ${v2 ? "V2" : "V1"}` : "Your booking entity"}/>
          <Metric icon={<ShieldAlert size={21}/>} label="Guard flags" value={conflicts} detail="Routed to analyst review"/>
          <Metric icon={<Database size={21}/>} label="FEBRL4 records" value={displayNumber(benchmark.leftRecords + benchmark.rightRecords)} detail="Independent linkage benchmark"/>
        </section>
        <section className="case-grid">
          <div className="panel queue-panel">
            <div className="panel-title"><h2>Cases</h2><ListFilter size={18}/></div>
            <label className="search"><Search size={17}/><input aria-label="Filter cases" placeholder="Search cases" value={filter} onChange={(e) => setFilter(e.target.value)}/></label>
            <div className="queue-rows">{rows.map((entry) => <button className={`case-row ${entry.id === selected?.id ? "selected" : ""}`}
              key={entry.id} type="button" onClick={() => setSelectedId(entry.id)} aria-pressed={entry.id === selected?.id}>
              <small>{entry.id} · {entry.booking_entity}</small><strong>{entry.title}</strong>
              <Status value={entry.packet.case_outcome.splink_with_guard}/>
            </button>)}{!rows.length && <p className="muted empty">No cases match this filter.</p>}</div>
            {mode === "demo" && !v2 && <button className="quiet-button alias-replay" onClick={loadV2}>Load V2 alias replay</button>}
            {feedMessage && <p className="inline-message" role="status">{feedMessage}</p>}
          </div>
          {selected ? <CaseDetail key={selected.id} selected={selected} history={history.filter((e) => e.case_id === selected.id)}
            allowResolve={mode === "demo" || profile?.review_role === "reviewer"} onSave={saveReview}/>
            : <section className="panel empty"><h2>No cases in scope</h2><p>Your booking entity has no imported screening cases.</p></section>}
        </section>
      </>}

      {view === "reviews" && <>
        {mode === "demo" && <RescreenReviews state={rescreenState} onOpen={(customer) => { setRescreenCustomer(customer); setView("rescreen"); }} />}
        <ReviewsPanel cases={modeCases} history={history} openCase={(id) => {
          setSelectedId(id); setFilter(""); setView("queue");
        }}/>
      </>}
      {view === "watchlists" && mode === "demo" && <WatchlistsPanel state={rescreenState} onState={commitRescreen} />}
      {view === "rescreen" && mode === "demo" && <RescreenDemo state={rescreenState} onState={commitRescreen} selected={rescreenCustomer} onSelect={setRescreenCustomer} />}
      {view === "benchmark" && <BenchmarkPanel data={benchmark}/>}
      {view === "feeds" && <section className="panel feed-panel">
        <div className="panel-title"><h2>Watchlist snapshots</h2><Database size={19}/></div>
        <div className="feed-row"><div><strong>OpenSanctions schema reference</strong><p>Fictional watchlist records with raw names, alias provenance and DOB precision.</p></div>
          <a className="quiet-button" href="https://www.opensanctions.org/reference/" target="_blank" rel="noreferrer">Data dictionary</a></div>
        {mode === "demo" ? <div className="feed-row"><div><strong>Local snapshot {v2 ? "V2" : "V1"}</strong><p>Replaying V2 brings in one documented alias case. Reloads keep a single alert.</p></div>
          <button className="primary" onClick={loadV2}>Load V2</button></div>
          : <div className="feed-row"><div><strong>Scoped Supabase case fetch</strong><p>V1 and V2 snapshot IDs are shown on the packets imported for your booking entity.</p></div></div>}
        <div className="feed-row"><div><strong>FEBRL4</strong><p>Upstream revision <code>{benchmark.revision.slice(0, 12)}</code>. Matching metrics were generated with Splink and DuckDB.</p></div>
          <a className="quiet-button" href={`https://github.com/J535D165/recordlinkage/tree/${benchmark.revision}/recordlinkage/datasets/febrl`} target="_blank" rel="noreferrer">Dataset source</a></div>
        {feedMessage && <p className="inline-message" role="status">{feedMessage}</p>}
      </section>}
    </main>
  </div>;
}

function ReviewsPanel({ cases, history, openCase }: { cases: Case[]; history: Review[]; openCase: (id: string) => void }) {
  const [processed, setProcessed] = useState(false);
  const rows = cases.map((entry) => ({ entry, review: history.find((item) => item.case_id === entry.id) }));
  const done = rows.filter(({ review }) => Boolean(review));
  const waiting = rows.filter(({ review }) => !review);
  const current = processed ? done : waiting;

  return <section className="panel review-queue">
    <div className="review-switch" aria-label="Review queue filter">
      <button type="button" aria-pressed={!processed} className={!processed ? "selected" : ""} onClick={() => setProcessed(false)}>Unprocessed <span>{waiting.length}</span></button>
      <button type="button" aria-pressed={processed} className={processed ? "selected" : ""} onClick={() => setProcessed(true)}>Processed <span>{done.length}</span></button>
    </div>
    <div className="table-scroll"><table><thead><tr><th>Case</th><th>Booking entity</th><th>{processed ? "Latest decision" : "Routing"}</th><th>Action</th></tr></thead>
      <tbody>{current.map(({ entry, review }) => <tr key={entry.id}>
        <td><strong>{entry.title}</strong><small>{entry.id}</small></td><td>{entry.booking_entity}</td>
        <td>{review ? <><span className={`status ${review.decision === "resolved" ? "good" : "warn"}`}>{decisionLabels[review.decision]}</span>
          <small className="review-timestamp"><time dateTime={review.created_at}>{new Date(review.created_at).toLocaleString()}</time></small></>
          : <Status value={entry.packet.case_outcome.splink_with_guard}/>}</td>
        <td><button className="quiet-button" onClick={() => openCase(entry.id)}>Open case</button></td>
      </tr>)}</tbody></table></div>
    {current.length === 0 && <p className="muted empty">{processed ? "No human decisions saved yet." : "Every visible case has a human decision."}</p>}
  </section>;
}

function CaseDetail({ selected, history, allowResolve, onSave }: {
  selected: Case; history: Review[]; allowResolve: boolean;
  onSave: (id: string, decision: Decision, rationale: string) => Promise<void>;
}) {
  const { packet } = selected;
  const [decision, setDecision] = useState<Decision>("awaiting_evidence");
  const [rationale, setRationale] = useState("");
  const [status, setStatus] = useState("");
  const [pending, setPending] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!rationale.trim()) return;
    setPending(true);
    try { await onSave(selected.id, decision, rationale.trim()); setRationale(""); setStatus("Review saved."); }
    catch (error) { setStatus(error instanceof Error ? error.message : "Could not save the review."); }
    finally { setPending(false); }
  }

  return <section className="panel detail-panel" aria-label="Case detail">
    <div className="case-top"><div><p className="case-ref">{selected.id} · {selected.booking_entity} · {selected.snapshot}</p>
      <h2>{selected.title}</h2><Status value={packet.case_outcome.splink_with_guard}/></div>
      <button className="quiet-button" onClick={() => downloadPacket(selected)}><ArrowDownToLine size={17}/>Evidence JSON</button></div>
    {selected.id === "CASE-08" && <div className="conflict-banner"><ShieldAlert size={20}/><div>
      <strong>Verified birth dates conflict</strong><p>A and C have different verified full dates of birth. The guard routes the chain to analyst review.</p>
    </div></div>}
    {packet.sanctions_list && <SanctionsDetail list={packet.sanctions_list} records={packet.records}/>}
    {selected.id === "CASE-03" && <div className="alias-banner"><ShieldCheck size={20}/><div>
      <strong>Documented alias surfaced this candidate</strong><p>The partial birth date remains visible as a gap for review.</p>
    </div></div>}
    {packet.ownership && <OwnershipEvidence ownership={packet.ownership} replay={selected.recommendation}/>}
    {packet.documents && <DocumentEvidence documents={packet.documents}/>}
    {packet.records.length > 0 && <div className="record-grid">{packet.records.map(({ record_id, tag, fields, source }) => <article key={record_id} className="record">
      <div className="record-top"><span className="record-token">{tag}</span><small>{record_id}</small></div>
      <strong>{fields.name.raw_value}</strong><p>{fields.dob.raw_value ?? "Birth date unknown"}</p>
      <small>{fields.dob.verification?.status === "verified" ? "Verified" : fields.dob.raw_value ? "Unverified" : "Unknown"} · {fields.dob.date_precision ?? "unknown"}</small>
      <details><summary>Source details</summary><p>{source.source_name}</p><code>{fields.dob.evidence_id}</code></details>
    </article>)}</div>}

    {packet.candidate_pairs.length > 0 && <><h3>Pair comparison</h3><div className="table-scroll"><table><thead><tr>
      <th>Pair</th><th>Name only</th><th>Splink</th><th>With guard</th>
    </tr></thead><tbody>{packet.candidate_pairs.map((pair) => <tr key={pair.pair_id}>
      <th scope="row">{pair.pair_name}</th>
      <td><strong>{pair.scores.name_only.score.toFixed(1)}</strong><Status value={pair.decisions.name_only}/></td>
      <td><strong>{pair.scores.splink?.match_probability == null ? "—" : percent(pair.scores.splink.match_probability)}</strong><Status value={pair.decisions.splink}/></td>
      <td><Status value={pair.decisions.splink_with_guard}/></td>
    </tr>)}</tbody></table></div>

    <div className="evidence-details">{packet.candidate_pairs.map((pair) => <details key={pair.pair_id}>
      <summary>{pair.pair_name} field contributions</summary>
      <ul>{pair.scores.splink?.field_contributions.map((item) => <li key={item.pair_evidence_id}>
        <strong>{item.field}</strong> · {item.level_description} · {item.match_weight.toFixed(2)} weight · <code>{item.pair_evidence_id}</code>
      </li>)}</ul>{pair.guard.reasons.map((reason) => <p key={reason}>{reason}</p>)}
    </details>)}</div></>}

    <form className="review-form" onSubmit={submit}>
      <h3>Analyst decision</h3><label>Disposition<select value={decision} onChange={(e) => setDecision(e.target.value as Decision)}>
        <option value="awaiting_evidence">Request more evidence</option>
        <option value="escalated_sanctions">Escalate to Sanctions</option>
        <option value="escalated_legal">Escalate to Legal</option>
        {allowResolve && <option value="resolved">Resolve</option>}
      </select></label>
      <label>Rationale<textarea value={rationale} onChange={(e) => setRationale(e.target.value)} rows={2} maxLength={1000} required/></label>
      <button className="primary" disabled={pending || !rationale.trim()}>{pending ? "Saving…" : "Save review"}</button>
      {status && <span role="status" className="review-feedback">{status}</span>}
    </form>
    {history.length > 0 && <section className="history"><h3>Review history</h3>{history.map((entry, index) =>
      <article key={`${entry.created_at}-${index}`}><strong>{decisionLabels[entry.decision]}</strong><time dateTime={entry.created_at}>{new Date(entry.created_at).toLocaleString()}</time><p>{entry.rationale}</p></article>
    )}</section>}
  </section>;
}

function BenchmarkPanel({ data }: { data: Benchmark }) {
  const [category, setCategory] = useState("All");
  const categories = [...new Set(data.examples.map((sample) => sample.category))];
  return <>
    <section className="metrics">
      <Metric icon={<Database size={21}/>} label="Synthetic records" value={displayNumber(data.leftRecords + data.rightRecords)} detail="Two source tables"/>
      <Metric icon={<Search size={21}/>} label="Candidates scored" value={displayNumber(data.candidatePairs)} detail={`${displayNumber(data.possiblePairs)} possible pairs`}/>
      <Metric icon={<Activity size={21}/>} label="Candidate recall" value={percent(data.retrievedTrue / data.labelledTrue)} detail={`${displayNumber(data.retrievedTrue)} / ${displayNumber(data.labelledTrue)} true pairs`}/>
    </section>
    <section className="panel benchmark-panel"><div className="panel-title"><h2>FEBRL4 results</h2><span className="synthetic-tag">Fixed settings</span></div>
      <div className="bars" aria-label="True links out of all labelled pairs">
        {([["RapidFuzz name only", data.methods.nameOnly], ["Splink · DuckDB", data.methods.splink]] as const).map(([name, value]) => <div key={name}>
          <div className="bar-label"><strong>{name}</strong><span>{displayNumber(value.trueLinks)} / {displayNumber(data.labelledTrue)}</span></div>
          <div className="bar-track"><div style={{ width: percent(value.trueLinks / data.labelledTrue) }}/></div>
          <p>{displayNumber(value.falseLinks)} false links · {displayNumber(value.missedTrue)} missed true links</p>
        </div>)}
      </div>
      <div className="method-note"><CircleHelp size={19}/><p>{displayNumber(data.retrievalMisses)} true pairs were missed at candidate generation. Both methods used the same candidate set. FEBRL4 does not provide DOB verification, so guard behaviour is exercised in the separate screening cases.</p></div>
      <details className="benchmark-method"><summary>Blocking, thresholds and versions</summary>
        <p>{data.configuration.blocking.join(" · ")}</p><p>RapidFuzz ≥ {data.configuration.nameThreshold} · Splink ≥ {percent(data.configuration.splinkThreshold)} · Scoring and retrieval {data.seconds}s on the recorded run</p>
        <p>Splink {data.versions.splink} · DuckDB {data.versions.duckdb} · RapidFuzz {data.versions.rapidfuzz}</p>
      </details>
    </section>
    <section className="panel samples"><div className="panel-title"><h2>Example pairs</h2>
      <select aria-label="Filter benchmark examples" value={category} onChange={(e) => setCategory(e.target.value)}><option>All</option>{categories.map((item) => <option key={item}>{item}</option>)}</select>
    </div><div className="table-scroll"><table><thead><tr><th>Source A</th><th>Source B</th><th>Name score</th><th>Splink</th><th>QA finding</th></tr></thead><tbody>
      {data.examples.filter((item) => category === "All" || item.category === category).map((item) => <tr key={item.id}>
        <td>{item.left ?? "Unknown"}</td><td>{item.right ?? "Unknown"}</td><td>{item.nameScore.toFixed(1)}</td>
        <td>{percent(item.splinkProbability)}</td><td>{item.category}</td>
      </tr>)}</tbody></table></div></section>
  </>;
}
