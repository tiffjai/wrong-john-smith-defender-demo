import type { ListEntryStatus, ListSnapshot, SanctionsList } from "./types";

export function observedEntryStatus(status: string): ListEntryStatus {
  if (status === "listed" || status === "removed" || status === "expired") return status;
  return "unconfirmed";
}

export function readSanctionsStatus(list: SanctionsList, asOf: string): {
  lastCheck?: ListSnapshot;
  status: ListEntryStatus | "stale";
} {
  const time = Date.parse(asOf);
  const lastCheck = list.snapshots
    .filter((entry) => Date.parse(entry.checked_at) <= time)
    .sort((a, b) => Date.parse(b.checked_at) - Date.parse(a.checked_at))[0];
  if (!lastCheck) return { status: "unconfirmed" };
  const age = time - Date.parse(lastCheck.checked_at);
  const status = age <= list.freshness_hours * 60 * 60 * 1000 ? observedEntryStatus(lastCheck.entry_status) : "stale";
  return { lastCheck, status };
}
