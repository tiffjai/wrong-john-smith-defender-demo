-- Allow escalated_mlro for new decisions; keep legacy escalated_sanctions valid for historical events.
alter table public.review_events drop constraint if exists review_events_decision_check;
alter table public.review_events add constraint review_events_decision_check
  check (decision in ('awaiting_evidence', 'escalated_mlro', 'escalated_legal', 'resolved', 'escalated_sanctions'));
