"use client";

import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import {
  Activity, ArrowDownToLine, ChartNoAxesCombined, CircleHelp, Database, FileSearch,
  ClipboardCheck, Fingerprint, Layers3, Library, ListFilter, LogOut, Search, ShieldAlert, ShieldCheck,
} from "lucide-react";
import EntityWorkspace from "./entity-workspace";
import type { ScreeningRun } from "../lib/entity-resolution";
import { signOut } from "./login/actions";
import { accessScopeLabel, type AnalystProfile } from "../lib/access-scope";
import type { Benchmark, Case, CaseNote, DashboardMode, Decision, Review } from "../lib/types";
import { initialRescreenState, readRescreenState, rescreenStorageKey, type CustomerKey, type RescreenState } from "../lib/rescreen";
import { DocumentEvidence, OwnershipEvidence } from "./case-evidence";
import SanctionsDetail from "./sanctions-detail";
import RescreenDemo from "./rescreen-demo";
import { CaseNotes } from "./case-notes";
import ResearchPanel from "./research-panel";
import { latestReview, reviewStage, stageLabels, type QueueStage } from "../lib/review-queue";
import WatchlistsPanel, { RescreenReviews } from "./watchlists";

const modes = [
  { id: "identity", label: "Identity review", icon: Fingerprint },
  { id: "queue", label: "Screening queue", icon: FileSearch },
  { id: "reviews", label: "Reviews", icon: ClipboardCheck },
  { id: "watchlists", label: "Watchlists", icon: Library },
  { id: "rescreen", label: "V2 rescreen demo", icon: Activity },
  { id: "benchmark", label: "FEBRL4 benchmark", icon: ChartNoAxesCombined },
  { id: "feeds", label: "Data sources", icon: Database },
] as const;
type View = typeof modes[number]["id"];

const decisionLabels: Record<Decision, string> = {
  awaiting_evidence: "Awaiting evidence", escalated_mlro: "Escalated to MLRO", escalated_sanctions: "Escalated to Sanctions (historical)",
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

function Metric({ icon, label, value, detail, onClick }: { icon: ReactNode; label: string; value: string | number; detail: string; onClick?: () => void }) {
  const content = <><div className="metric-icon">{icon}</div><div>
    <p>{label}</p><strong>{value}</strong><small>{detail}</small>
  </div></>;
  return onClick ? <button type="button" className="metric metric-link" onClick={onClick}>{content}</button>
    : <div className="metric">{content}</div>;
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

export default function Dashboard({ mode, cases, benchmark, reviews, notes: initialNotes, viewerId, profile, screeningRun }: {
  screeningRun?: ScreeningRun | null;
  mode: DashboardMode; cases: Case[]; benchmark: Benchmark; reviews: Review[]; notes: CaseNote[]; viewerId?: string;
  profile?: AnalystProfile;
}) {
  const [view, setView] = useState<View>(mode === "demo" ? "identity" : "queue");
  const [queueSource, setQueueSource] = useState<"imported" | "cases">("imported");
  const datasetQueue = !!screeningRun && !screeningRun.synthetic && (mode === "demo" || (screeningRun.storage === "supabase" && queueSource === "imported"));
  const datasetView = view === "identity" || (view === "queue" && datasetQueue);
  const [selectedId, setSelectedId] = useState(cases[0]?.id);
  const [history, setHistory] = useState(reviews);
  const [notes, setNotes] = useState(initialNotes);
  const [v2, setV2] = useState(false);
  const [feedMessage, setFeedMessage] = useState("");
  const [filter, setFilter] = useState("");
  const [demoRole, setDemoRole] = useState<"junior" | "senior">("junior");
  const role = mode === "demo" ? demoRole : profile?.review_role === "reviewer" ? "senior" : "junior";
  const [queueFilter, setQueueFilter] = useState<QueueStage | "all">("all");
  const [reviewFilter, setReviewFilter] = useState<QueueStage | "all">("all");
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
    if (decision === "resolved" && role !== "senior") throw new Error("A senior analyst must close the case.");
    if (mode === "supabase") {
      const response = await fetch("/api/reviews", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ case_id: caseId, decision, rationale }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.error ?? "Could not save this review.");
      setHistory((events) => [body as Review, ...events]);
    } else {
      const entry = { case_id: caseId, decision, rationale, created_at: new Date().toISOString(), reviewer_role: role };
      const next = [entry, ...history];
      localStorage.setItem("defender-review-events", JSON.stringify(next));
      setHistory(next);
    }
  }

  const modeCases = mode === "demo" && !v2 ? cases.filter((entry) => entry.snapshot === "V1") : cases;
  const rows = modeCases.filter((entry) => (queueFilter === "all" || reviewStage(history, entry.id) === queueFilter)
    && `${entry.id} ${entry.title} ${entry.booking_entity}`.toLowerCase().includes(filter.trim().toLowerCase()));
  const selected = rows.find((entry) => entry.id === selectedId) ?? rows[0];
  const countStage = (stage: QueueStage) => modeCases.filter((entry) => reviewStage(history, entry.id) === stage).length;
  function openReviews(stage: QueueStage) { setReviewFilter(stage); setView("reviews"); }
  const subtitle = view === "identity" ? "Per-hit identity decisions, linked records and traceable evidence." : view === "queue" ? datasetQueue ? "Latest screening dataset · Alerts grouped with per-hit findings and supporting evidence." : role === "junior"
    ? "Junior analyst · Investigate screening alerts, gather evidence and escalate cases."
    : "Senior analyst · Review escalations, challenge the evidence and make the final decision."
    : view === "reviews" ? "Track open work, escalations and completed decisions. Open a case to review its evidence."
    : view === "watchlists" ? "Load a snapshot, then manually rescreen the two enrolled customers."
    : view === "rescreen" ? "Propose and approve the two V1 closures. Load and rescreen from Watchlists."
    : view === "benchmark" ? "Compare two matchers on the same FEBRL4 candidate pairs."
    : "Inspect the demo snapshots and the benchmark’s provenance.";

  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><div className="brand-emblem"><Fingerprint size={23} /></div>
        <div>Defender<small>Identity screening</small></div></div>
      {(!datasetView || mode === "supabase") && <section className="role-panel" aria-label="Analyst workspace">
        <span className="role-caption">{mode === "demo" ? "Demo workspace" : "Your assigned workspace"}</span>
        {mode === "demo" ? <div className="role-switch" aria-label="Analyst view">
          {(["junior", "senior"] as const).map((value) => <button key={value} type="button" aria-pressed={role === value}
            className={role === value ? "selected" : ""} onClick={() => { setDemoRole(value); setQueueFilter(value === "senior" ? "escalated" : "pending"); setFilter(""); }}>
            {value === "junior" ? "Junior Analyst" : "Senior Analyst"}</button>)}
        </div> : <strong>{role === "senior" ? "Senior Analyst" : "Junior Analyst"}</strong>}
        <small>{role === "junior" ? "Investigate & escalate" : "Review & close cases"}</small>
      </section>}
      <div className="navigation-group"><span className="navigation-label">WORKSPACE</span><nav aria-label="Workspace">
        {modes.filter(({ id }) => mode === "demo" || (id !== "rescreen" && id !== "watchlists")).map(({ id, label, icon: Icon }) => <button key={id} type="button" onClick={() => setView(id)}
          className={id === view ? "nav-button active" : "nav-button"} aria-current={id === view ? "page" : undefined}>
          <Icon size={18}/><span>{label}</span>
        </button>)}
      </nav></div>
      <div className="sidebar-bottom">
        <div className="workspace-tag"><Activity size={16}/>{datasetView ? screeningRun?.storage === "supabase" ? "Supabase screening run" : "Local screening run" : mode === "demo" ? "Offline demo" : "Supabase connected"}</div>
        <div className="workspace-caption">{profile ? `${accessScopeLabel(profile)} · ${role === "senior" ? "Senior Analyst" : "Junior Analyst"}` : datasetView && screeningRun ? "Participant dataset" : "Synthetic records"}</div>
        {mode === "supabase" && <form action={signOut}><button className="signout"><LogOut size={16}/>Sign out</button></form>}
      </div>
    </aside>

    <main className="workspace">
      <div className="workspace-topbar"><div><ShieldCheck size={16}/><span>Defender workspace</span><span className="topbar-divider">/</span><strong>{modes.find((entry) => entry.id === view)?.label}</strong></div><span className="workspace-security"><span/> Evidence-led screening</span></div>
      <header className="workspace-header"><div><span className="workspace-eyebrow">IDENTITY INTELLIGENCE</span>
        <h1>{modes.find((entry) => entry.id === view)?.label}</h1><p>{subtitle}</p>
      </div><span className="synthetic-tag"><ShieldCheck size={16}/>{datasetView && screeningRun && !screeningRun.synthetic ? (screeningRun.storage === "supabase" ? "Imported participant data" : "Local participant data") : "Synthetic data"}</span></header>

      {view === "identity" && <>
        {mode === "supabase" && <p className="demo-banner" role="note">{screeningRun
          ? "This screening run is stored in Supabase. Automated findings and evidence are preserved; no human approvals or closures were imported. FEBRL4 remains a separate linkage benchmark."
          : "No screening run is assigned to this workspace. Identity review starts with a synthetic walkthrough; your Supabase cases remain in Screening queue."} This view does not change live case decisions.</p>}
        <EntityWorkspace key={screeningRun?.generatedAt} initialRun={screeningRun}/>
      </>}
      {view === "queue" && screeningRun?.storage === "supabase" && <div className="review-switch" aria-label="Screening queue source">
        <button className={queueSource === "imported" ? "selected" : ""} aria-pressed={queueSource === "imported"} onClick={() => setQueueSource("imported")}>Imported alerts ({new Set(screeningRun.predictions.map(hit => hit.alert_id)).size})</button>
        <button className={queueSource === "cases" ? "selected" : ""} aria-pressed={queueSource === "cases"} onClick={() => setQueueSource("cases")}>Demo cases ({modeCases.length})</button>
      </div>}
      {view === "queue" && datasetQueue && <EntityWorkspace key={screeningRun?.generatedAt} initialRun={screeningRun} queueMode/>}
      {view === "queue" && !datasetQueue && <>
        <section className="metrics" aria-label="Case review summary">
          <Metric icon={<Layers3 size={21}/>} label="Pending analyst action" value={countStage("pending")} detail="New alerts or awaiting evidence · View reviews →" onClick={() => openReviews("pending")}/>
          <Metric icon={<ShieldAlert size={21}/>} label="Escalated for review" value={countStage("escalated")} detail="Senior / specialist attention · View reviews →" onClick={() => openReviews("escalated")}/>
          <Metric icon={<ClipboardCheck size={21}/>} label="Completed cases" value={countStage("resolved")} detail="Closed by a senior analyst · View history →" onClick={() => openReviews("resolved")}/>
        </section>
        <div className="queue-context"><p><strong>{modeCases.length} screening alerts</strong> · {mode === "demo" ? `Snapshot ${v2 ? "V2" : "V1"}` : profile ? accessScopeLabel(profile) : "Your booking entity"}. Automated screening has run; open alerts still need a human decision.</p>
          <button className="text-button" onClick={() => setView("benchmark")}>View separate matching benchmark →</button></div>
        <section className="case-grid">
          <div className="panel queue-panel">
            <div className="panel-title"><h2>{role === "senior" ? "Senior review queue" : "Investigation queue"}</h2><ListFilter size={18}/></div>
            <label className="queue-filter">Case status<select value={queueFilter} onChange={(event) => setQueueFilter(event.target.value as QueueStage | "all")}>
              <option value="all">All cases ({modeCases.length})</option>
              {(["pending", "escalated", "resolved"] as const).map((stage) => <option key={stage} value={stage}>{stageLabels[stage]} ({countStage(stage)})</option>)}
            </select></label>
            <label className="search"><Search size={17}/><input aria-label="Filter cases" placeholder="Search cases" value={filter} onChange={(e) => setFilter(e.target.value)}/></label>
            <div className="queue-rows">{rows.map((entry) => <button className={`case-row ${entry.id === selected?.id ? "selected" : ""}`}
              key={entry.id} type="button" onClick={() => setSelectedId(entry.id)} aria-pressed={entry.id === selected?.id}>
              <small>{entry.id} · {entry.booking_entity}</small><strong>{entry.title}</strong>
              <span className={`status ${reviewStage(history, entry.id) === "resolved" ? "good" : "warn"}`}>{stageLabels[reviewStage(history, entry.id)]}</span>
            </button>)}{!rows.length && <p className="muted empty">No cases match this filter.</p>}</div>
            {mode === "demo" && !v2 && <button className="quiet-button alias-replay" onClick={loadV2}>Load V2 alias replay</button>}
            {feedMessage && <p className="inline-message" role="status">{feedMessage}</p>}
          </div>
          {selected ? <CaseDetail key={`${selected.id}-${role}`} selected={selected} history={history.filter((e) => e.case_id === selected.id)}
            allowResolve={role === "senior"} onSave={saveReview} notes={notes} canAnnotate={mode === "supabase"} viewerId={viewerId} onNoteCreated={(note) => setNotes(current => [note, ...current])}/>
            : <section className="panel empty"><h2>No cases in this queue</h2><p>{queueFilter === "escalated" ? "No escalations need attention. Junior analysts can continue their investigations." : "Try another status or search term."}</p><button className="quiet-button" onClick={() => { setQueueFilter("all"); setFilter(""); }}>Show all cases</button></section>}
        </section>
      </>}

      {view === "reviews" && <>
        {mode === "demo" && <RescreenReviews state={rescreenState} onOpen={(customer) => { setRescreenCustomer(customer); setView("rescreen"); }} />}
        <ReviewsPanel cases={modeCases} history={history} stage={reviewFilter} setStage={setReviewFilter} openCase={(id) => {
          setSelectedId(id); setFilter(""); setQueueFilter("all"); setView("queue");
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

function ReviewsPanel({ cases, history, stage, setStage, openCase }: {
  cases: Case[]; history: Review[]; stage: QueueStage | "all";
  setStage: (stage: QueueStage | "all") => void; openCase: (id: string) => void;
}) {
  const rows = cases.filter((entry) => stage === "all" || reviewStage(history, entry.id) === stage);
  return <section className="panel review-queue">
    <div className="panel-title"><h2>Review progress & history</h2><ClipboardCheck size={20}/></div>
    <p className="muted">An evidence request or escalation stays open. Only a senior analyst’s resolution completes a case.</p>
    <div className="review-switch" aria-label="Review queue filter">
      {(["all", "pending", "escalated", "resolved"] as const).map((value) => <button key={value} type="button" aria-pressed={stage === value}
        className={stage === value ? "selected" : ""} onClick={() => setStage(value)}>
        {value === "all" ? "All cases" : stageLabels[value]} <span>{cases.filter((entry) => value === "all" || reviewStage(history, entry.id) === value).length}</span>
      </button>)}
    </div>
    <div className="table-scroll"><table><thead><tr><th>Case</th><th>Booking entity</th><th>Review status</th><th>Latest decision</th><th>Action</th></tr></thead>
      <tbody>{rows.map((entry) => {
        const review = latestReview(history, entry.id);
        return <tr key={entry.id}>
          <td><strong>{entry.title}</strong><small>{entry.id}</small></td><td>{entry.booking_entity}</td>
          <td><span className={`status ${review?.decision === "resolved" ? "good" : "warn"}`}>{stageLabels[reviewStage(history, entry.id)]}</span></td>
          <td>{review ? <>{decisionLabels[review.decision]}<small className="review-timestamp"><time dateTime={review.created_at}>{new Date(review.created_at).toLocaleString()}</time></small></> : "No human decision yet"}</td>
          <td><button className="quiet-button" onClick={() => openCase(entry.id)}>{review?.decision === "resolved" ? "View case & history" : "Review case"}</button></td>
        </tr>;
      })}</tbody></table></div>
    {!rows.length && <p className="muted empty">No cases in this status.</p>}
  </section>;
}

function CaseDetail({ selected, history, allowResolve, onSave, notes, canAnnotate, viewerId, onNoteCreated }: {
  selected: Case; history: Review[]; allowResolve: boolean; notes: CaseNote[]; canAnnotate: boolean; viewerId?: string;
  onNoteCreated: (note: CaseNote) => void;
  onSave: (id: string, decision: Decision, rationale: string) => Promise<void>;
}) {
  const { packet } = selected;
  const [decision, setDecision] = useState<Decision>(allowResolve ? "resolved" : "awaiting_evidence");
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
      <h2>{selected.title}</h2><span className={`status ${reviewStage(history, selected.id) === "resolved" ? "good" : "warn"}`}>{stageLabels[reviewStage(history, selected.id)]}</span><p className="screening-result">Automated screening: <Status value={packet.case_outcome.splink_with_guard}/></p></div>
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

    <CaseNotes caseId={selected.id} notes={notes} canAnnotate={canAnnotate} viewerId={viewerId} onCreated={onNoteCreated}/>
    <ResearchPanel key={selected.id} selected={selected}/>
    <form className="review-form" onSubmit={submit}>
      <h3>{allowResolve ? "Senior analyst decision" : "Junior analyst assessment"}</h3><p className="muted">{allowResolve ? "Review the evidence and assessment history before closing or escalating the case." : "Document your findings, request evidence or escalate. Only a senior analyst can close a case."}</p><label>Disposition<select value={decision} onChange={(e) => setDecision(e.target.value as Decision)}>
        <option value="awaiting_evidence">Request more evidence</option>
        <option value="escalated_mlro">Escalate to MLRO</option>
        <option value="escalated_legal">Escalate to Legal</option>
        {allowResolve && <option value="resolved">Resolve</option>}
      </select></label>
      <label>Rationale<textarea value={rationale} onChange={(e) => setRationale(e.target.value)} rows={2} maxLength={1000} required/></label>
      <button className="primary" disabled={pending || !rationale.trim()}>{pending ? "Saving…" : allowResolve ? "Save senior decision" : "Save assessment"}</button>
      {status && <span role="status" className="review-feedback">{status}</span>}
    </form>
    {history.length > 0 && <section className="history"><h3>Review history</h3>{history.map((entry, index) =>
      <article key={`${entry.created_at}-${index}`}><strong>{decisionLabels[entry.decision]}</strong>{entry.reviewer_role && <small> · {entry.reviewer_role === "senior" ? "Senior Analyst" : "Junior Analyst"}</small>}<time dateTime={entry.created_at}>{new Date(entry.created_at).toLocaleString()}</time><p>{entry.rationale}</p></article>
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
