"use client";

import { useState } from "react";
import { CalendarClock } from "lucide-react";
import { observedEntryStatus, readSanctionsStatus } from "../lib/sanctions-list";
import type { Packet, SanctionsList } from "../lib/types";

const statusText = {
  listed: "Listed in this snapshot",
  removed: "Removed from this demo list",
  expired: "Designation expired",
  unconfirmed: "List status unconfirmed",
  stale: "Feed stale · status unconfirmed",
};
const statusDescription = {
  listed: "The latest checked snapshot shows this entry as listed.",
  removed: "The latest checked snapshot records an explicit removal. The earlier listing is retained in history.",
  expired: "The latest check records a designation end date. The earlier listing is retained in history.",
  unconfirmed: "There is no confirmed listing status for the selected check time.",
  stale: "The last successful check is outside the freshness window. Recheck the source before relying on its status.",
};
const timestamp = new Intl.DateTimeFormat("en-GB", {
  dateStyle: "medium", timeStyle: "short", timeZone: "Europe/London",
});

export default function SanctionsDetail({ list, records }: { list: SanctionsList; records: Packet["records"] }) {
  const [simulateStale, setSimulateStale] = useState(false);
  const asOf = simulateStale
    ? new Date(Date.parse(list.fixture_as_of) + (list.freshness_hours + 1) * 3600000).toISOString()
    : list.fixture_as_of;
  const { status, lastCheck } = readSanctionsStatus(list, asOf);
  const subject = records.find((record) => record.record_id === list.subject_record_id);
  const customer = records.find((record) => record.tag === "A" && record.record_id !== list.subject_record_id);

  return <section className="sanctions-detail" aria-labelledby="sanctions-title">
    <div className="panel-title"><h3 id="sanctions-title">Sanctions list and listing status</h3><span className="status quiet">Synthetic source</span></div>
    <div className="sanctions-list-summary">
      <div><h4>{list.name}</h4><p>{list.regime} · <code>{list.entry_id}</code></p></div>
      <span className={`status ${status === "removed" || status === "expired" ? "quiet" : "warn"}`} role="status">{statusText[status]}</span>
    </div>
    <dl className="sanctions-identity">
      {subject && <div><dt>Listed identity in history · Record {subject.tag}</dt>
        <dd>{subject.fields.name.raw_value} · DOB {subject.fields.dob.raw_value}</dd><dd><code>{subject.fields.dob.evidence_id}</code></dd></div>}
      {customer && <div><dt>Customer under review · Record {customer.tag}</dt>
        <dd>{customer.fields.name.raw_value} · DOB {customer.fields.dob.raw_value}</dd><dd>No confirmed link to this entry · <code>{customer.fields.dob.evidence_id}</code></dd></div>}
    </dl>
    <div className="sanctions-check"><CalendarClock size={19}/><div>
      <p>{statusDescription[status]}</p>
      <small>Demo check time {timestamp.format(new Date(asOf))} London time.
        {lastCheck && <> Last successful check {timestamp.format(new Date(lastCheck.checked_at))} · <code>{lastCheck.snapshot_id}</code>.</>}
        {status === "stale" && lastCheck && <> Last observed status: {statusText[observedEntryStatus(lastCheck.entry_status)]}.</>}</small>
    </div></div>
    <p className="sanctions-grounds"><strong>Designation grounds</strong> {list.grounds}. <strong>Source</strong> <code>{list.source_id}</code>.</p>
    <details className="sanctions-history" open>
      <summary>Listing history</summary>
      <div className="table-scroll"><table><thead><tr><th>Snapshot</th><th>Entry status</th><th>Effective date</th><th>Evidence</th></tr></thead>
        <tbody>{[...list.snapshots].reverse().map((event) => <tr key={event.snapshot_id}>
          <td><code>{event.snapshot_id}</code><small>Published {timestamp.format(new Date(event.published_at))}</small></td>
          <td>{statusText[observedEntryStatus(event.entry_status)]}</td><td>{event.effective_on}</td><td><code>{event.evidence_id}</code></td>
        </tr>)}</tbody></table></div>
    </details>
    <button type="button" className="quiet-button" onClick={() => setSimulateStale(!simulateStale)} aria-pressed={simulateStale}>
      {simulateStale ? "Return to latest demo check" : "Simulate stale feed"}
    </button>
  </section>;
}
