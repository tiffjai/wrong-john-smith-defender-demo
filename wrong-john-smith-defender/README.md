# Wrong John Smith Defender — Track 3 synthetic screening demo (milestone 1)

**Synthetic data only.** Every person, name, date, ID, place and source is fictional. The dashboard supports an
analyst; the analyst makes the final screening decision. Nothing here is published or networked: the app makes no
network calls at runtime (network is needed only for the one-off `pip install`).

## Launch (one command)

```bash
./run.sh            # creates .venv, installs pinned deps, starts http://127.0.0.1:8501
```

Other commands: `./run.sh test` (pytest), `./run.sh evaluate`, `./run.sh export`, `./run.sh check`
(headless start + `/_stcore/health` + page probe, then stop). Deep link to a case: `/?case=CASE-08`.
Needs Python ≥ 3.11 (tested on 3.13.5, Linux x86_64). Pins: `requirements.txt` (runtime), `requirements-dev.txt` (+pytest).

## Scenarios (3 of the brief's cases)

| Case | Brief | Records | Candidate pairs |
|---|---|---|---|
| CASE-01 (#01) | same-name decoy, conflicting **verified full** DOBs | A, B | A–B |
| CASE-03 (#03) | plausible match via a **sourced Cantonese/Pinyin alias** (`ALIAS-0001`, source `SRC-SYN-ALIAS-001`) | A "Wong Siu Ming", B "Huang Xiaoming" (DOB `Jul 1988`, unverified) | A–B (found only via the alias block) |
| CASE-08 (#08) | misleading chain; A and C have contradictory verified full DOBs | A, B (DOB unknown), C | A–B, B–C and the direct A–C comparison |

The scenario names/titles live only in `evaluation/labels.json` (shown in the dashboard's Evaluation tab behind a toggle),
not in the data, the scoring code or the packets.

## How it works

```
data/records.json + data/alias_table.json
        │ defender/data.py (normalise; raw values kept; unknown stays None)
        ▼
 candidate pairs  (blocking: same case & same family name  OR  same case & same documented alias group)
        │  generated once in Python and cross-checked against Splink's own blocked pairs (error on any difference)
        ├──► 1 name-only   RapidFuzz token_sort_ratio on normalised full name     → LINK / REVIEW / NO_LINK
        ├──► 2 Splink 4 (DuckDB): name, dob, country, city comparisons             → LINK / REVIEW / NO_LINK
        └──► 3 Splink + deterministic guard (defender/guard.py)                    → may escalate to REVIEW
```

* **Splink without EM.** With 5 synthetic pairs, EM training is unstable and would just fit noise. All m/u
  probabilities, the prior (0.01) and the thresholds are fixed in `config/draft_config.json` and frozen. Splink is used
  as the scoring engine (blocking, comparison levels, Bayes factors, match weights). They are builder-chosen
  illustrative values, **not fitted or validated**; the test suite checks that each Splink Bayes factor equals m/u of the chosen level and that the
  probability recomputes from the contributions.
* **DOB comparison respects precision.** Levels: full exact / year+month agree (a date lacks its day) / year agrees (a date lacks its month) /
  differ at the shared precision; unknown on either side → neutral level (BF = 1). Splink does not see verification status.
* **Guard.** Contradiction = both DOBs **full precision and verified** and different. Partial, unverified, unknown or
  unparseable dates are `not_assessable` — never a contradiction, never imputed. Guard escalates LINK/REVIEW pairs with a direct
  contradiction to REVIEW, and also chain-checks: records joined by Splink LINK edges form a component; if any pair in
  it contradicts, every pair in the component goes to REVIEW (that is how A–B and B–C in CASE-08 are caught even though neither
  has a direct contradiction). The guard never hides a pair or lowers a score.
* **Alias.** Aliases come only from `data/alias_table.json`; an entry without a `source_id` is rejected. An alias gives a candidate and a strong
  name level, but cannot override a contradiction.
* **Frozen thresholds.** `python scripts/freeze_config.py` writes `config/frozen_config.json` (`frozen_at` + `config_sha256`
  over parameters and the SHA-256 of the records/alias inputs). Pipeline and evaluation call `load_frozen()` and raise
  if anything changed after freezing. Evaluation records `frozen_at`, `evaluated_at`, and the config hash with its results.
* **Labels are separate.** `evaluation/labels.json` is read only by `evaluation/evaluate.py` (and the dashboard's Evaluation tab).
  Nothing in `defender/` imports or opens it (static + dynamic tests), and packets contain no label keys/values (test).

## Dashboard

Case selector (sidebar) → raw records table (raw values, normalised DOB, date precision, verification status/method/source, source IDs) →
three columns over the **same** pairs → chain view (CASE-08) → per-pair evidence (name-only score, Splink field contributions with m/u/BF/weight,
guard check) → analyst review (Undecided / Confirm match / Not a match / Escalate + note; saved to `reviews/analyst_reviews.json`,
not into packets) → JSON evidence packet download. Evaluation tab: FP, missed true matches, manual-review pairs, candidate recall, each as n/d per method.
Method tab: frozen parameters and the alias table.

## Evidence packet (`exports/evidence_packet_<CASE>.json`)

`case_id`, `records[]` (source id/name/type, per-field `evidence_id`, `raw_value`, `normalised_value`, `date_precision`, `verification`),
`candidate_pairs[]` (blocking rules, alias evidence with source id, name-only score, Splink weight/probability + `field_contributions[]`
with pair evidence IDs, guard outcome/reasons/DOB check), `chain_analysis`, `case_outcome`, and `model` (frozen parameters + hash so a reviewer can recompute).
Evidence IDs are `EV-` + first 12 hex of SHA-256 over `[record_id, source_id, field, raw_value]`, so they are stable across runs. The packet has no timestamps, so
regeneration is byte-identical (tested). No evaluation labels.

## Measured counts (this milestone; 5 candidate pairs, 2 labelled true matches, 3 labelled non-matches)

| Method | False positives (auto-linked non-matches) | Missed true matches | Manual-review pairs | Candidate recall |
|---|---|---|---|---|
| Name-only (RapidFuzz) | 3/3 | 1/2 | 0/5 | 2/2 |
| Splink | 2/3 | 0/2 | 0/5 | 2/2 |
| Splink + guard | 0/3 | 0/2 | 4/5 | 2/2 |

Without the alias table: 4 candidate pairs, candidate recall 1/2 (CASE-03 is never generated). Full output in `verification/`.
These numbers show the pipeline working on hand-built scenarios; they are **not** evidence of real-world accuracy.

## Limitations

* Three hand-built scenarios; parameters were chosen by the builder who knew them (no held-out data). Thresholds are frozen *before the evaluation run*, but not tuned on independent data.
* Candidate generation is scoped to a case (records are only compared inside their case) and uses family-name / alias blocking only.
* The guard is DOB-only. Other verified identifiers (IDs, nationality) are out of scope for this milestone.
* `DD/MM/YYYY` raw dates are parsed day-first (documented assumption).
* The analyst review store is a local JSON file, single user, no authentication.
* Scenarios #02, #04–#07 and #09+ of the brief are not implemented yet.

---

# Milestone 2 — Track 3 synthetic rescreening (`rescreen/`, `rescreen_qa/`)

Milestone 1 is unchanged: the original files are untouched, its 45 tests still pass, and `exports/evidence_packet_CASE-0{1,3,8}.json` are byte-identical to the hashes in `verification_rescreen/milestone1_expected_sha256.txt`. The rescreen package reuses the milestone-1 scorer as is: RapidFuzz name-only, Splink 4/DuckDB with fixed, documented m/u and no training, the verified-full-DOB guard, the same candidate pairs, and the frozen config `config/frozen_config.json` (sha pinned in `rescreen/config/frozen_policy.json`). No new dependencies. The demo is fully offline and makes no live Grok call.

**Demo.** The fictional watchlist entry DEMO-WL-410 "CHAN Wai Man" (陳偉文) is on the fictional UK list FICT-UK-SL, with V1 DOB 1987-09-03. There are two synthetic customers:
- RESCREEN-A: SYN-CUST-A "Chan Wai Man", DOB 1979-04-11. The verified national ID differs from the list ID, and V2 does not change that.
- RESCREEN-B: SYN-CUST-B "Chan Wei Man", DOB 1991-06-14 (verified passport), documented alias "Chan Wai Mun".

V2, published 2026-11-15, corrects the list DOB to 1991-06-14 and adds the Cantonese romanisation "Chan Wai Mun". There is also a malformed V3 for the failure path, plus fictional US (FICT-US-SL) and Mainland China (FICT-CN-ML) lists.

## Run commands
```bash
./run_rescreen.sh acceptance   # fresh DB, steps 1-9, 24 checks; writes exports/rescreen/*.json; exit 0 only if all pass
./run_rescreen.sh qa           # threshold replay -> exports/rescreen/qa_replay.json
./run_rescreen.sh api          # JSON API at http://127.0.0.1:8765 (DB rescreen_state/api.sqlite, created on first start)
./run_rescreen.sh ui           # secondary Streamlit check view at http://127.0.0.1:8502
./run_rescreen.sh test         # full pytest: milestone 1 + rescreen
./run_rescreen.sh release      # every release check; output captured in verification_rescreen/
./run_rescreen.sh sweep        # daily sweep entry point; cron example: 0 6 * * * /path/run_rescreen.sh sweep
./run_rescreen.sh cli --help   # python -m rescreen: reset, load-feed, propose, approve, case, packet, handoff, jurisdictions, ...
```
The CLI drives the same flow step by step:
- `./run_rescreen.sh cli reset --db rescreen_state/x.sqlite`
- `... cli load-feed UK V2 --db ...`
- `... cli case RESCREEN-B --db ...`

## Next.js integration

The contract version is `rescreen-contract/1.0` (`views.CONTRACT_VERSION`; every payload carries `contract_version` and `synthetic: true`). JSON Schemas (draft 2020-12) are in `rescreen/schema/`: `case_view`, `evidence_packet`, `challenger_handoff`, `reviews`, `jurisdictions`, `feeds_status` and `qa_replay`. The release checks validate every export against them.

**Option 1: static files** (no server). Read `exports/rescreen/`:

| File | Screen |
|---|---|
| `case_view_RESCREEN-{A,B}.json` | Case view: header, names/aliases/original script, current screening (3 methods), `evidence_side_by_side` (V1/V2 columns), `earlier_rationale_and_decisions`, pending proposal, events, `allowed_actions`, `ai.challenger` (live unavailable + labelled replay) |
| `reviews.json` | Reviews: `pending[]` vs `completed[]` (decision, validity CURRENT/INVALIDATED, proposer, reviewer, basis, evidence IDs) |
| `feeds_status.json`, `jobs.json` | Feed health / coverage / last-good; rescreen jobs |
| `evidence_packet_*.json` | Label-free evidence packet |
| `challenger_handoff_*.json` | Changed fields + approval basis + evidence IDs only |
| `jurisdictions_RESCREEN-{A,B}_{UK,US,CN}.json` | UK/US/CN evidence view for each primary jurisdiction |
| `qa_replay.json` | QA threshold replay |
| `acceptance_report.json` | 24 checks with observed values |

The exports come from a simulated clock that starts at 2026-11-21T09:00:00Z and adds 1 minute per action, so they are deterministic. Set `RESCREEN_REAL_CLOCK=1` to use wall-clock time.

**Option 2: local API** (`./run_rescreen.sh api`; stdlib `http.server`, bound to 127.0.0.1).
- CORS allows `http://localhost:3000` and `http://127.0.0.1:3000`. A Next.js `rewrites()` proxy to `http://127.0.0.1:8765/api/:path*` also works.
- POSTs take the actor from the `X-Demo-Actor` header or the body field `actor`. This is a simulated sign-in using the seeded roles in `rescreen/fixtures/actors.json`:

| Actor | Role |
|---|---|
| ana.analyst, sam.analyst | analyst |
| rio.senior, kai.senior | senior_reviewer |
| lee.legal | legal_reviewer |
| adm.screening | screening_admin |

| Method & path | Body | Result |
|---|---|---|
| GET `/api/health` | | `{status, contract_version, grok_live:false, routes}` |
| GET `/api/feeds` · `/api/jobs` · `/api/cases` · `/api/reviews` | | feed status · jobs · alert queue · pending/completed |
| GET `/api/cases/{id}` · `/packet` · `/challenger-handoff` · `/jurisdictions?primary=UK\|US\|CN` | | case view · packet · handoff · jurisdiction view |
| POST `/api/demo/reset` | | fresh DB, V1 loaded, initial screening |
| POST `/api/feeds/load` | `{jurisdiction:"UK", version:"V2"}` | `ACTIVATED` (+ rescreen job) / `NO_UPDATE` / `FAILED_VALIDATION` |
| POST `/api/feeds/simulate-failure` | `{jurisdiction?}` | malformed V3 rejected; last-good kept |
| POST `/api/jobs/sweep` · `/api/jobs/{job_id}/retry` | | daily sweep (same job function) · retry a failed job |
| POST `/api/customers/{customer_id}` | `{changes:{field:value}}` | KYC version; a material change triggers a rescreen |
| POST `/api/cases/{id}/propose` | `{rationale, evidence_ids, basis_type, customer_evidence_id, list_evidence_id}` | analyst proposes a false-positive closure |
| POST `/api/cases/{id}/approve` · `/return` | `{comment}` | a different senior approves or returns |
| POST `/api/cases/{id}/request-evidence` · `/escalate` | `{comment}` · `{queue, comment}` | AWAITING_EVIDENCE · ESCALATED |
| POST `/api/cases/{id}/ai-response` | `{suggestion_id, action: ACCEPT\|AMEND\|REJECT, text}` | human response, stored separately from the AI text |

**Error codes:**
- `403` for role or self-approval errors: `{error: ROLE_NOT_ALLOWED | SELF_APPROVAL_FORBIDDEN | UNKNOWN_ACTOR}`.
- `409` for workflow errors (`BAD_STATE`, `BASIS_INVALID`, `UNKNOWN_EVIDENCE`, `RATIONALE_REQUIRED`, …).
- `404` for an unknown id. A missing required body field also returns `404`; treat it as a bad request.
- `400` for invalid JSON.

**Basis types:**
- `verified_identifier_conflict` cites the national_id evidence IDs.
- `verified_full_dob_conflict` cites the dob evidence IDs.

Take the IDs from `current_evidence[]` in the case view. On every rescreen the basis is re-evaluated:
- `HOLDS`: the approval stays CURRENT.
- `CITED_EVIDENCE_SUPERSEDED` or `BASIS_NO_LONGER_HOLDS`: the case reopens and the approval becomes INVALIDATED. It is kept in the history, never deleted.

Further detail and expected results are in `QA_HANDOFF.md`.
