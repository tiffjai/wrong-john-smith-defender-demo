import type { Review } from "./types";

export type QueueStage = "pending" | "escalated" | "resolved";
export const stageLabels: Record<QueueStage, string> = {
  pending: "Pending analyst action", escalated: "Escalated for review", resolved: "Completed",
};

export function latestReview(history: Review[], caseId: string) {
  return history.filter((entry) => entry.case_id === caseId)
    .reduce<Review | undefined>((latest, entry) => !latest || Date.parse(entry.created_at) > Date.parse(latest.created_at) ? entry : latest, undefined);
}

export function reviewStage(history: Review[], caseId: string): QueueStage {
  const decision = latestReview(history, caseId)?.decision;
  if (decision === "resolved") return "resolved";
  if (decision === "escalated_legal" || decision === "escalated_mlro" || decision === "escalated_sanctions") return "escalated";
  return "pending";
}
