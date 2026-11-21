export type Field = {
  evidence_id: string;
  raw_value: string | null;
  normalised_value: string | null;
  date_precision?: string;
  verification?: { status: string; source_id: string | null };
};

export type Pair = {
  pair_id: string;
  pair_name: string;
  alias_evidence: object | null;
  scores: {
    name_only: { score: number };
    splink: {
      match_probability: number | null;
      field_contributions: { pair_evidence_id: string; field: string; level_description: string; match_weight: number }[];
    } | null;
  };
  decisions: { name_only: string; splink: string; splink_with_guard: string };
  guard: { reasons: string[]; outcome: string };
};

export type Packet = {
  case_id: string;
  synthetic: boolean;
  schema_version: string;
  case_outcome: { name_only: string; splink: string; splink_with_guard: string };
  records: {
    record_id: string;
    tag: string;
    source: { source_id: string; source_name: string };
    fields: { name: Field; dob: Field; city: Field; country: Field };
  }[];
  candidate_pairs: Pair[];
  ownership?: {
    as_of: string;
    maximum_registry_age_days: number;
    company: string;
    direct_checks: SourceFinding[];
    links: { parent: string; child: string; percentage: number; observed_on: string; evidence_id: string; source: string }[];
    related_alert: SourceFinding;
  };
  documents?: IdentityDocument[];
  sanctions_list?: SanctionsList;
};

export type ListEntryStatus = "listed" | "removed" | "expired" | "unconfirmed";
export type ListSnapshot = {
  snapshot_id: string; evidence_id: string; published_at: string; checked_at: string;
  entry_status: string; effective_on: string;
};
export type SanctionsList = {
  name: string; regime: string; source_id: string; entry_id: string; subject_record_id: string;
  grounds: string; fixture_as_of: string; freshness_hours: number; snapshots: ListSnapshot[];
};

type SourceFinding = { company: string; result: string; evidence_id: string; source: string; observed_on: string };
export type IdentityDocument = {
  evidence_id: string; customer_id: string; name: string; issuer: string;
  display_number: string; document_key: string; issued: string; expires: string;
  verified_dob: string; verification_source: string; replaces: string | null; superseded_on: string | null;
};

export type Recommendation = { case_id: string; evidence_ids: string[]; review_priority: string; suggested_next_check: string;
  contradictions: { finding: string; evidence_ids: string[] }[]; missing_evidence: { finding: string; evidence_ids: string[] }[] };
export type Case = { id: string; title: string; booking_entity: string; snapshot: string; packet: Packet; recommendation?: Recommendation | null };
export type Decision = "awaiting_evidence" | "escalated_mlro" | "escalated_sanctions" | "escalated_legal" | "resolved";
export type Review = { reviewer_role?: "junior" | "senior"; case_id: string; decision: Decision; rationale: string; created_at: string };
export type DashboardMode = "demo" | "supabase";
export type Benchmark = typeof import("../data/benchmark.json");

export type CaseNote = { id: string; case_id: string; author_id: string; body: string; created_at: string };
