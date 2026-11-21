"use client";

import { useMemo, useRef, useState } from "react";
import { ArrowDownToLine, ArrowRight, CheckCheck, FileUp, Fingerprint, GitBranch, Search, ShieldAlert, Users } from "lucide-react";
import { assessAlerts, assessHit, type RiskBand } from "../lib/risk";
import { RiskBadge, RiskMethodology } from "./risk-dashboard";
import { groupAlerts, identityDecisions, parsePredictions, type AlertReview, type IdentityDecision, type IdentityTrace, type Prediction, type ScreeningRun } from "../lib/entity-resolution";

const labels: Record<IdentityDecision, string> = { DIFFERENT_ENTITY: "Different entity", SAME_ENTITY: "Same entity", REVIEW: "Needs review" };
const statusClass: Record<IdentityDecision, string> = { DIFFERENT_ENTITY: "good", SAME_ENTITY: "match", REVIEW: "warn" };
const synthetic: Prediction[] = [
  { alert_id: "DEMO-01", hit_id: "HIT-01", customer_record_id: "CRM-01", decision: "DIFFERENT_ENTITY", reason_code: "DOB_MISMATCH", reason: "The approved identity check gives a customer DOB of 1988-03-14. The listed subject was born in 1952, outside the SOP's one-year tolerance.", evidence: ["CRM-01", "KYC-01", "HIT-01"] },
  { alert_id: "DEMO-01", hit_id: "HIT-02", customer_record_id: "CRM-01", decision: "REVIEW", reason_code: "INSUFFICIENT_DATA", reason: "The second namesake has no usable birth date or location. The evidence cannot settle this hit, so the whole alert remains open.", evidence: ["CRM-01", "HIT-02"] },
  { alert_id: "DEMO-02", hit_id: "HIT-03", customer_record_id: "CRM-02", decision: "SAME_ENTITY", reason_code: "NAME_DOB_MATCH", reason: "The verified name Li Wei and full DOB 1975-02-18 agree with the listed subject. No contradiction is present in this synthetic example.", evidence: ["CRM-02", "KYC-02", "HIT-03"] },
];
export default function EntityWorkspace({ initialRun, queueMode = false, allowClose = false, initialAlertId, savedReviews, onReviewClosed }: { initialRun?: ScreeningRun | null; queueMode?: boolean; allowClose?: boolean; initialAlertId?: string; savedReviews?: AlertReview[]; onReviewClosed?: (review: AlertReview) => void }) {
  const baseline = useMemo<ScreeningRun>(() => initialRun ?? { source: "Synthetic walkthrough", synthetic: true, predictions: synthetic, traces: {} }, [initialRun]);
  const [run, setRun] = useState<ScreeningRun>(baseline);
  const [selectedId, setSelectedId] = useState(run.predictions.find(hit => hit.alert_id === initialAlertId)?.hit_id ?? run.predictions[0]?.hit_id);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<IdentityDecision | "ALL">("ALL");
  const [alertFilter, setAlertFilter] = useState<"ALL" | "OPEN" | "CLEAR" | "CLOSED">("ALL");
  const [localReviews, setReviews] = useState<AlertReview[]>(baseline.reviews ?? []);
  const reviews = savedReviews ?? localReviews;
  const [riskFilter, setRiskFilter] = useState<RiskBand | "ALL">("ALL");
  const [riskSort, setRiskSort] = useState("source");
  const riskItems = useMemo(() => assessAlerts(run, run === baseline ? reviews : []), [run, baseline, reviews]);
  const riskByAlert = useMemo(() => new Map(riskItems.map(item => [item.id, item])), [riskItems]);
  const [rationale, setRationale] = useState("");
  const [saving, setSaving] = useState(false);
  const [feedback, setFeedback] = useState("");
  const [error, setError] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);
  const alerts = useMemo(() => groupAlerts(run.predictions).map(alert => ({ ...alert, reviewed: run === baseline && reviews.some(review => review.alert_id === alert.id) })), [run, baseline, reviews]);
  const tracesByHit = useMemo(() => {
    const index = new Map<string, IdentityTrace[]>();
    Object.entries(run.traces).forEach(([key, trace]) => { const hitId = key.split(":")[0]; index.set(hitId, [...(index.get(hitId) ?? []), trace]); });
    return index;
  }, [run]);
  const rows = useMemo(() => run.predictions.filter(row => (filter === "ALL" || row.decision === filter) && `${row.alert_id} ${row.hit_id} ${row.customer_record_id} ${(tracesByHit.get(row.hit_id) ?? []).map(trace => `${trace.customer.name} ${trace.watchlist.name}`).join(" ")} ${row.reason_code} ${row.reason} ${row.evidence.join(" ")}`.toLowerCase().includes(query.toLowerCase())), [run, query, filter, tracesByHit]);
  const visibleAlerts = alerts.filter(alert => (riskFilter === "ALL" || riskByAlert.get(alert.id)?.band === riskFilter) && alert.hits.some(hit => rows.includes(hit)) && (alertFilter === "ALL" || (alertFilter === "CLOSED" ? alert.reviewed : alertFilter === "CLEAR" ? alert.closed : !alert.closed && !alert.reviewed))).sort((a, b) => riskSort === "risk" ? (riskByAlert.get(b.id)?.score ?? 0) - (riskByAlert.get(a.id)?.score ?? 0) || a.id.localeCompare(b.id) : 0);
  const visibleAlertIds = new Set(visibleAlerts.map(alert => alert.id));
  const visibleRows = rows.filter(row => visibleAlertIds.has(row.alert_id));
  const selected = visibleRows.find(row => row.hit_id === selectedId) ?? visibleRows[0];
  const alert = alerts.find(a => a.id === selected?.alert_id);
  const traces = selected ? (tracesByHit.get(selected.hit_id) ?? []) : [];
  const trace = traces[0];
  const selectedRisk = selected ? assessHit(selected, traces) : null;
  const counts = (decision: IdentityDecision) => run.predictions.filter(row => row.decision === decision).length;
  const exportRun = () => {
    const href = URL.createObjectURL(new Blob([run.predictions.map(row => JSON.stringify(row)).join("\n") + "\n"], { type: "application/x-ndjson" }));
    const anchor = document.createElement("a"); anchor.href = href; anchor.download = run.synthetic ? "synthetic-predictions.jsonl" : "predictions.jsonl"; anchor.click(); setTimeout(() => URL.revokeObjectURL(href), 1000);
  };
  return <div className="identity-workspace">
    <div className="identity-intro"><div><span className="identity-eyebrow">{queueMode ? "SCREENING QUEUE" : "IDENTITY REVIEW"}</span><h2>{queueMode ? "Review screening alerts" : "Same person or not?"}</h2><p>{queueMode ? "Open an alert to inspect its hits, customer identity and supporting evidence." : "Resolve the customer. Resolve the listed subject. Compare the evidence."}</p></div><div className="rescreen-actions">{!queueMode && <button className="quiet-button" onClick={() => fileInput.current?.click()}><FileUp size={16}/>Import predictions</button>}<button className="primary" onClick={exportRun}><ArrowDownToLine size={16}/>Export JSONL</button></div></div>
    <input ref={fileInput} type="file" accept=".jsonl,.ndjson" hidden aria-label="Import prediction JSONL" onChange={async event => {
      const file = event.target.files?.[0]; if (!file) return;
      try { if (file.size > 20 * 1024 * 1024) throw new Error("Choose a prediction file smaller than 20 MB."); const predictions = parsePredictions(await file.text()); setRun({ source: file.name, synthetic: false, predictions, traces: {} }); setSelectedId(predictions[0].hit_id); setRiskFilter("ALL"); setAlertFilter("ALL"); setFilter("ALL"); setQuery(""); setError(""); } catch (e) { setError(e instanceof Error ? e.message : "Could not import predictions."); } finally { event.target.value = ""; }
    }}/>
    {error && <p className="conflict-banner" role="alert">{error}</p>}
    <div className="identity-source"><span className="source-dot"/><strong>{run.source}</strong><span>{run.synthetic ? "Invented examples" : run === baseline ? run.storage === "supabase" ? "Participant data · stored in Supabase" : "Participant data · local workspace" : "Imported file · source unverified"}</span><span>{run.predictions.length} hits · {alerts.length} alerts{run.durationSeconds != null ? ` · ${run.durationSeconds}s run` : ""}</span>{run.generatedAt && <span>Updated {new Date(run.generatedAt).toLocaleString("en-GB", { timeZone: "Europe/London" })} (London)</span>}{run !== baseline && <button className="text-button" onClick={() => { setRun(baseline); setRiskFilter("ALL"); setAlertFilter("ALL"); setFilter("ALL"); setQuery(""); }}>Restore workspace results</button>}</div>
    <section className="risk-cards risk-workspace-cards" aria-label="Alert risk summary">{(["High", "Medium", "Low"] as const).map(band => <button key={band} className={`risk-card risk-${band.toLowerCase()} ${riskFilter === band ? "is-selected" : ""}`} aria-pressed={riskFilter === band} onClick={() => setRiskFilter(riskFilter === band ? "ALL" : band)}><span>{band} risk</span><strong>{riskItems.filter(item => item.band === band).length}</strong><small>{riskItems.filter(item => item.band === band && item.status === "Open").length} open alerts</small></button>)}</section>
    <section className="metrics identity-metrics" aria-label="Identity outcomes">
      {identityDecisions.map(decision => <button key={decision} className={`metric metric-link ${filter === decision ? "metric-selected" : ""}`} onClick={() => setFilter(filter === decision ? "ALL" : decision)} aria-pressed={filter === decision}><div className={`metric-icon outcome-${decision}`}>{decision === "DIFFERENT_ENTITY" ? <CheckCheck size={22}/> : decision === "SAME_ENTITY" ? <Users size={22}/> : <ShieldAlert size={22}/>}</div><div><p>{labels[decision]}</p><strong>{counts(decision)}</strong><small>{decision === "DIFFERENT_ENTITY" ? "Evidence supports exclusion" : decision === "SAME_ENTITY" ? "Identity agrees · retain alert" : "Human judgment required"}</small></div></button>)}
    </section>
    <div className="identity-progress"><CheckCheck size={17}/><strong>{alerts.filter(a => a.closed).length} of {alerts.length} alerts clear</strong><span>Every hit must be different to clear an alert.</span><span className="identity-principle">Identity findings are separate from compliance decisions.</span></div>
    <div className="identity-grid">
      <section className="panel identity-results"><div className="panel-title"><h2>{queueMode ? "Screening alerts" : "Screening hits"}</h2><span>{queueMode ? `${visibleAlerts.length} alerts` : `${visibleRows.length} shown`}</span></div>
        <label className="search"><Search size={17}/><input aria-label="Search screening hits" placeholder="Search alerts, hits or evidence…" value={query} onChange={e => setQuery(e.target.value)}/></label>
        {queueMode && <label className="queue-filter">Alert status<select value={alertFilter} onChange={e => setAlertFilter(e.target.value as typeof alertFilter)}><option value="ALL">All alerts ({alerts.length})</option><option value="OPEN">Open ({alerts.filter(a => !a.closed && !a.reviewed).length})</option><option value="CLEAR">Clear ({alerts.filter(a => a.closed).length})</option><option value="CLOSED">Closed reviews ({alerts.filter(a => a.reviewed).length})</option></select></label>}
        <label className="queue-filter">Risk level<select value={riskFilter} onChange={event => setRiskFilter(event.target.value as typeof riskFilter)}><option value="ALL">All risk levels</option>{(["High", "Medium", "Low"] as const).map(band => <option key={band}>{band}</option>)}</select></label>
        {queueMode && <label className="queue-filter">Sort screening alerts<select value={riskSort} onChange={event => setRiskSort(event.target.value)}><option value="source">Source order</option><option value="risk">Highest risk first</option></select></label>}
        <label className="queue-filter identity-filter">Identity decision<select value={filter} onChange={e => setFilter(e.target.value as typeof filter)}><option value="ALL">All decisions</option>{identityDecisions.map(d => <option key={d} value={d}>{labels[d]}</option>)}</select></label>
        <div className="identity-hit-list">{queueMode ? visibleAlerts.map(item => {
          const hit = item.hits.find(h => visibleRows.includes(h))!;
          const names = [...new Set(item.hits.flatMap(h => tracesByHit.get(h.hit_id) ?? []).map(trace => trace.customer.name))];
          return <button key={item.id} className={`identity-hit ${selected?.alert_id === item.id ? "selected" : ""}`} onClick={() => { setSelectedId(hit.hit_id); setRationale(""); setFeedback(""); }} aria-pressed={selected?.alert_id === item.id}><span className="case-ref">{item.id}</span><strong>{names.join(" / ") || hit.customer_record_id || "Unresolved customer"}<ArrowRight size={15}/></strong><span className={`status ${item.closed || item.reviewed ? "good" : "warn"}`}>{item.reviewed ? "Closed" : item.closed ? "Clear" : "Open"}</span><RiskBadge {...riskByAlert.get(item.id)!}/><small>{item.hits.length} hits · {item.hits.filter(h => h.decision === "SAME_ENTITY").length} same · {item.hits.filter(h => h.decision === "REVIEW").length} need review</small></button>;
        }) : visibleRows.map(row => <button key={row.hit_id} className={`identity-hit ${selected?.hit_id === row.hit_id ? "selected" : ""}`} onClick={() => setSelectedId(row.hit_id)} aria-pressed={selected?.hit_id === row.hit_id}><span className="case-ref">{row.alert_id}</span><strong>{row.hit_id}<ArrowRight size={15}/></strong><span className={`status ${statusClass[row.decision]}`}>{labels[row.decision]}</span><small>{row.reason_code.replaceAll("_", " ").toLowerCase()}</small></button>)}{!(queueMode ? visibleAlerts.length : visibleRows.length) && <p className="empty muted">No matching hits. Change the decision filter or search.</p>}</div>
      </section>
      {selected && <section className="panel detail-panel identity-detail" aria-label="Identity evidence">
        <div className="case-top"><div><p className="identity-eyebrow">{selected.alert_id} / {selected.hit_id}</p><h2>{selected.customer_record_id === "AMBIGUOUS" ? "Ambiguous customer identity" : trace?.customer.name ?? selected.customer_record_id ?? "Unresolved customer"}</h2><p className="muted">Compared with {trace?.watchlist.name ?? "listed subject"}</p></div><span className={`status ${statusClass[selected.decision]}`}>{labels[selected.decision]}</span></div>
        {selectedRisk && <section className="hit-risk-explanation"><div className="panel-title"><h3>Screening risk score</h3><RiskBadge {...selectedRisk}/></div><p>Hit score: {selectedRisk.score}/100 · Alert score: {riskByAlert.get(selected.alert_id)?.score}/100 (highest hit)</p><ul>{selectedRisk.drivers.map(driver => <li key={driver.label}><strong>+{driver.points} {driver.label}</strong><span>{driver.detail}</span></li>)}</ul><p><strong>Next step:</strong> {selectedRisk.nextAction}</p></section>}
        <div className={`identity-conclusion conclusion-${selected.decision}`}><span className="identity-eyebrow">DECISIVE FINDING</span><h3>{selected.reason_code.replaceAll("_", " ").toLowerCase()}</h3><p>{selected.reason}</p></div>
        {traces.length > 1 && <p className="conflict-banner">{traces.length} distinct customer people fit. All candidate comparisons are shown below; the customer record remains AMBIGUOUS.</p>}
        {traces.length > 0 ? traces.map((item, i) => <IdentityComparison key={i} trace={item} ambiguous={traces.length > 1}/>) : <div className="identity-no-trace"><Fingerprint size={23}/><div><strong>Record-level evidence</strong><p>{run.synthetic ? "This synthetic walkthrough illustrates the output contract." : "Prediction files contain decisions and evidence IDs. Importing predictions alone does not supply the underlying source records."}</p></div></div>}
        <section className="identity-evidence"><h3>Decisive evidence IDs</h3><div className="evidence-tokens">{selected.evidence.map(id => <code key={id}>{id}</code>)}</div><small>Exact source record IDs supplied by the resolver. Missing fields are never evidence of a mismatch.</small></section>
        {run === baseline && <section className="review-form" key={selected.alert_id}>
          <h3>Senior review</h3>
          {alert?.reviewed ? <><span className="status good">Closed — no escalation required</span>{reviews.filter(review => review.alert_id === selected.alert_id).map(review => <article key={review.created_at}><p>{review.rationale}</p><small>{new Date(review.created_at).toLocaleString()}</small></article>)}</> : allowClose ? <form onSubmit={async event => {
            event.preventDefault();
            if (!rationale.trim() || saving) return;
            const alertId = selected.alert_id;
            setSaving(true); setFeedback("");
            try {
              let review: AlertReview;
              if (run.storage === "supabase") {
                const response = await fetch("/api/screening-reviews", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ import_id: run.importId, alert_id: alertId, rationale: rationale.trim() }) });
                const result = await response.json();
                if (!response.ok) throw new Error(result.error ?? "Could not close the review.");
                review = result;
              } else {
                review = { alert_id: alertId, rationale: rationale.trim(), created_at: new Date().toISOString() };
              }
              setReviews(current => [review, ...current]); onReviewClosed?.(review); setRationale(""); setFeedback("Review closed — no escalation required.");
            } catch (error) { setFeedback(error instanceof Error ? error.message : "Could not close the review."); }
            finally { setSaving(false); }
          }}><p>Close this alert after reviewing every hit if nothing is suspicious and no escalation is needed. Automated identity findings remain visible.</p>
            <label>Closure rationale<textarea required maxLength={1000} rows={3} value={rationale} onChange={event => setRationale(event.target.value)}/></label>
            <button className="primary" disabled={saving || !rationale.trim()}>{saving ? "Closing…" : "Close review — no escalation required"}</button>
            {run.storage !== "supabase" && <p className="muted">Demo closure stays in this session.</p>}
          </form> : <p>Only a senior analyst can close this review.</p>}
          {feedback && <p role="status">{feedback}</p>}
        </section>}
        <section className="identity-alert"><div className="panel-title"><h3>Alert {selected.alert_id}</h3><span className={`status ${alert?.reviewed || alert?.closed ? "good" : "warn"}`}>{alert?.reviewed ? "Closed" : alert?.closed ? "Clear" : "Open"}</span></div><p>{alert?.reviewed ? "A senior analyst closed this review with no escalation required. Automated findings are preserved below." : alert?.closed ? "Every hit in this alert is a different entity." : "At least one hit is a match or unresolved. This alert stays open for human review."}</p><div className="identity-siblings">{alert?.hits.map(h => <button key={h.hit_id} className="quiet-button" onClick={() => { setSelectedId(h.hit_id); setFilter("ALL"); setQuery(""); }}>{h.hit_id} · {labels[h.decision]}</button>)}</div></section>
      </section>}
    </div>
    <RiskMethodology/>
    <p className="identity-footer">Deterministic rules · Approved identity checks take precedence · No live web or language model calls · {run === baseline && run.storage === "supabase" ? "Baseline findings and evidence stored in Supabase · File previews stay in this page’s memory" : "Imports stay in this page’s memory"}</p>
  </div>;
}
function IdentityComparison({ trace, ambiguous }: { trace: IdentityTrace; ambiguous: boolean }) {
  const format = (date: number[] | null) => date?.map((part, i) => i ? String(part).padStart(2, "0") : String(part)).join("-") ?? "Unknown";
  return <section className="identity-comparison"><h3>Two identities, one comparison</h3><div className="identity-two-sides"><article><span className="identity-eyebrow">{ambiguous ? "CANDIDATE CUSTOMER" : "RESOLVED CUSTOMER"}</span><h3>{trace.customer.name}</h3><dl><dt>Birth / incorporation date</dt><dd>{format(trace.customer.dob)}</dd><dt>Known countries</dt><dd>{trace.customer.countries.join(", ") || "Unknown"}</dd><dt>Identity source</dt><dd>{trace.customer.verified ? "Latest approved identity evidence" : "Declared customer record"}</dd></dl></article><article><span className="identity-eyebrow">LISTED SUBJECT</span><h3>{trace.watchlist.name}</h3><dl><dt>Possible birth / incorporation dates</dt><dd>{trace.watchlist.dobs.map(format).join(" or ") || <span style={{ textTransform: "none" }}>Missing — cannot compare</span>}</dd><dt>Known countries</dt><dd>{trace.watchlist.countries.join(", ") || "Unknown"}</dd><dt>Earliest qualifying report</dt><dd>{format(trace.watchlist.report)}</dd></dl></article></div><div className="identity-path"><GitBranch size={16}/><strong>Customer linkage</strong><p>{trace.path.join(" → ")}</p></div>{trace.gaps.length > 0 && <div className="identity-gaps"><strong>Missing evidence</strong><ul>{trace.gaps.map(gap => <li key={gap}>{gap}</li>)}</ul></div>}</section>;
}
