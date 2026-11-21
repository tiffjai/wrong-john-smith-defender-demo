import { Files, ShieldAlert } from "lucide-react";
import { compareDocuments } from "../lib/document-checks";
import type { IdentityDocument, Packet, Recommendation } from "../lib/types";

export function OwnershipEvidence({ ownership, replay }: { ownership: NonNullable<Packet["ownership"]>; replay?: Recommendation | null }) {
  return <section className="special-evidence">
    <div className="conflict-banner"><ShieldAlert size={20}/><div><strong>Possible exposure through ownership</strong>
      <p>A related-party alert and an old parent register need human verification.</p></div></div>
    <h3>Screening and ownership evidence</h3>
    {ownership.direct_checks.map((item) => <p className="finding" key={item.evidence_id}>
      <strong>{item.result}</strong> for {item.company} · <code>{item.evidence_id}</code><br/>
      <small>{item.source} · {item.observed_on}</small>
    </p>)}
    <div className="table-scroll"><table><thead><tr><th>Owner</th><th>Company</th><th>Reported stake</th><th>Source</th></tr></thead>
      <tbody>{ownership.links.map((link) => {
        const age = (Date.parse(ownership.as_of) - Date.parse(link.observed_on)) / 86400000;
        return <tr key={link.evidence_id}><td>{link.parent}</td><td>{link.child}</td><td>{link.percentage}%</td>
          <td><code>{link.evidence_id}</code><br/>{link.source}<br/>{link.observed_on}
            {age > ownership.maximum_registry_age_days && <><br/><span className="status warn">Stale register</span></>}
          </td></tr>;
      })}</tbody></table></div>
    <p className="finding"><strong>{ownership.related_alert.result}</strong> for {ownership.related_alert.company} · <code>{ownership.related_alert.evidence_id}</code><br/>
      <small>{ownership.related_alert.source} · {ownership.related_alert.observed_on}</small></p>
    {replay && <section className="grok-card" aria-label="Original Grok recommendation"><div className="panel-title"><h3>Grok recommendation</h3>
      <span className="status quiet">Saved replay</span></div>
      {replay.missing_evidence.map((finding) => <p key={finding.finding}>{finding.finding} <code>{finding.evidence_ids.join(", ")}</code></p>)}
      <p><strong>Next check</strong> {replay.suggested_next_check}</p>
      <details><summary>Original JSON and citations</summary><pre>{JSON.stringify(replay, null, 2)}</pre></details>
    </section>}
  </section>;
}

export function DocumentEvidence({ documents }: { documents: IdentityDocument[] }) {
  const { overlaps, conflicts } = compareDocuments(documents);
  const customers = Array.from(new Set(documents.map((document) => document.customer_id)));
  return <section className="special-evidence">
    {conflicts.map(([a,b]) => <div className="conflict-banner" key={a.evidence_id + b.evidence_id}><ShieldAlert size={20}/><div>
      <strong>Document identity conflict · hold any automatic merge</strong>
      <p>{a.customer_id} and {b.customer_id} share a synthetic document key, with conflicting verified DOBs {a.verified_dob} and {b.verified_dob}. <code>{a.evidence_id}, {b.evidence_id}</code></p>
    </div></div>)}
    {overlaps.map(([a,b]) => <div className="alias-banner" key={a.evidence_id + b.evidence_id}><Files size={20}/><div>
      <strong>Overlapping validity · consistent identity evidence</strong>
      <p>{a.customer_id} has overlapping document dates and the same verified DOB. <code>{a.evidence_id}, {b.evidence_id}</code></p>
    </div></div>)}
    <h3>Identity document timeline</h3>
    {customers.map((customer) => <div key={customer} className="timeline"><h4>{customer}</h4>
      {documents.filter((item) => item.customer_id === customer).sort((a,b) => a.issued.localeCompare(b.issued)).map((item) =>
        <article className="timeline-row" key={item.evidence_id}>
          <div><strong>{item.display_number}</strong><small>{item.issuer}</small></div>
          <div><strong>{item.name}</strong><small>{item.issued} to {item.expires}</small></div>
          <div><code>{item.evidence_id}</code><small>{item.verification_source}</small>
            {item.replaces && <small>Replaces {item.replaces}</small>}
            {item.superseded_on && <small>Superseded on {item.superseded_on}</small>}</div>
        </article>)}
    </div>)}
  </section>;
}
