"use client";

import { useState } from "react";
import type { Case } from "../lib/types";
import type { ResearchAction, ResearchPhoto, ResearchReport } from "../lib/research-types";

function ReferencePhoto({ photo }: { photo: ResearchPhoto }) {
  const [failed, setFailed] = useState(false);
  return <figure className="reference-photo">
    {failed ? <div className="photo-unavailable">Image unavailable. Open the source page to inspect it.</div>
      : <img src={photo.url} alt="Unverified image from the linked source page" loading="lazy" referrerPolicy="no-referrer" onError={() => setFailed(true)}/>}
    <figcaption><span className="status warn">Subject unverified</span><p>{photo.description}</p>
      <a href={photo.source_url} target="_blank" rel="noopener noreferrer">{photo.source_title}</a>
      <small><code>{photo.evidence_id}</code></small>
    </figcaption>
  </figure>;
}

export default function ResearchPanel({ selected }: { selected: Case }) {
  const [query, setQuery] = useState(selected.packet.ownership?.company ?? selected.packet.records[0]?.fields.name.raw_value ?? "");
  const [url, setUrl] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [reports, setReports] = useState<ResearchReport[]>([]);
  const listedSubject = selected.packet.records.find(record => record.record_id === selected.packet.sanctions_list?.subject_record_id);

  async function run(action: ResearchAction, sourceUrl = url) {
    setPending(true); setError("");
    try {
      const response = await fetch("/api/research", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ case_id: selected.id, action, query, url: sourceUrl }) });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error ?? "Research failed.");
      setReports(previous => [result, ...previous].slice(0, 10));
    } catch (err) { setError(err instanceof Error ? err.message : "Research failed."); }
    finally { setPending(false); }
  }

  function download() {
    const blob = new Blob([JSON.stringify({ case_id: selected.id, research: reports }, null, 2)], { type: "application/json" });
    const href = URL.createObjectURL(blob);
    const anchor = document.createElement("a"); anchor.href = href; anchor.download = `${selected.id}-web-research.json`; anchor.click(); URL.revokeObjectURL(href);
  }

  return <section className="research-panel" aria-label="Tavily research">
    <h3>Web evidence research · Tavily</h3>
    <p>Fictional demo identities may share names with real people. Edit the terms before searching. Terms and source URLs are sent to Tavily when you run a check. Add a country, company or other public context to reduce namesake results.</p>
    <label>Research terms<input value={query} onChange={event => setQuery(event.target.value)} maxLength={400} /></label>
    <div className="research-actions">
      <button className="quiet-button" disabled={pending || query.trim().length < 2} onClick={() => run("official")}>1. Search official sources</button>
      <button className="quiet-button" disabled={pending || query.trim().length < 2} onClick={() => run("news")}>2. Search recent adverse media</button>
      <button className="quiet-button" disabled={pending || query.trim().length < 2} onClick={() => run("photos")}>Find reference photos</button>
    </div>
    <p className="photo-help"><small>{listedSubject && <>Listed record: <strong>{listedSubject.fields.name.raw_value}</strong>. </>}Photo search uses the research terms above and official source pages. Photos may show other people, logos or unrelated images; confirm the list entry and identity before use. Loading images contacts the image host. Synthetic demo records have no verified portrait.</small></p>
    <p><small>Official checks cover government sanctions and UK company registry sources. News searches cover the past month; add terms such as fraud, sanctions or investigation as needed.</small></p>
    <label>Public source URL<input type="url" placeholder="https://…" value={url} onChange={event => setUrl(event.target.value)} maxLength={2000}/></label>
    <div className="research-actions"><button className="quiet-button" disabled={pending || !url || query.trim().length < 2} onClick={() => run("extract")}>3. Extract source text</button>
      {reports.length > 0 && <button className="quiet-button" onClick={download}>Export research JSON</button>}</div>
    {pending && <p role="status">Researching sources…</p>}
    {error && <p role="alert">{error}</p>}
    <p><strong>Human verification required.</strong> A name match is a lead, and no results does not mean cleared. Web research does not change matching or case decisions.</p>
    {reports.map((report, index) => <article className="research-report" key={`${report.retrieved_at}-${index}`}>
      <h4>{report.action === "photos" ? "Reference photos · identity unverified" : report.action === "official" ? "Official sources" : report.action === "news" ? "Recent media" : "Extracted source"}</h4>
      <p>{report.query}<br/><small>Retrieved {report.retrieved_at} · {report.case_id}</small></p>
      <p>{report.warning}</p>
      {report.action === "photos" && <>{report.photos?.length
        ? <div className="reference-photos">{report.photos.map(photo => <ReferencePhoto key={photo.evidence_id} photo={photo}/>)}</div>
        : <p role="status">No source-attributed photos returned. This does not establish whether the person is listed. Check the original list entry.</p>}</>}
      {report.sources.length === 0 && <p>No usable sources returned. Request further evidence if needed.</p>}
      {report.failed_urls.map(failed => <p key={failed}>Extraction failed: {failed}</p>)}
      {report.sources.map(source => <div className="research-source" key={source.evidence_id}>
        <a href={source.url} target="_blank" rel="noopener noreferrer">{source.title}</a>
        <p><code>{source.evidence_id}</code>{source.published_at && <> · Published {source.published_at}</>}</p>
        <details><summary>View unverified source text</summary><pre>{source.content}</pre></details>
        {report.action !== "extract" && <button className="quiet-button" disabled={pending} onClick={() => { setUrl(source.url); void run("extract", source.url); }}>Extract this source</button>}
      </div>)}
    </article>)}
    <small>Research stays in this case view for this session (latest 10 runs). Export before switching cases.</small>
  </section>;
}
