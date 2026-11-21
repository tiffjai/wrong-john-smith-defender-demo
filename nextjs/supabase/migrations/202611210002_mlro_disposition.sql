begin;

-- Retain legacy sanctions events as recorded; new reviews use MLRO.
alter table public.review_events drop constraint review_events_decision_check;
alter table public.review_events add constraint review_events_decision_check
  check (decision in ('awaiting_evidence', 'escalated_mlro', 'escalated_sanctions', 'escalated_legal', 'resolved'));

commit;
