# QA handoff — Track 3 synthetic rescreening (milestone 2)

All data is synthetic, and all lists and measures are fictional. Everything runs offline, with no live Grok. Run from the project root.

**One command:** `./run_rescreen.sh release` runs checks R1–R7 and captures their output in `verification_rescreen/`. It ends with `RELEASE CHECKS: PASS` and exit code 0.

## Release checks

| # | Check | Command | Expected result |
|---|---|---|---|
| R1 | Full test suite (milestone 1 + rescreen) | `./run_rescreen.sh test` | 69 passed (45 milestone 1 + 24 rescreen) |
| R2 | End-to-end acceptance | `./run_rescreen.sh acceptance` | `RESULT: 24/24 checks passed`, exit 0 |
| R3 | Threshold replay | `./run_rescreen.sh qa` | P1 loses SYN-08-A\|SYN-08-B at `SCORING`; P2 loses SYN-03-A\|SYN-03-B at `RETRIEVAL`; both `HELD_FOR_REVIEW` |
| R4 | Exports match the JSON Schemas | part of `release` | `validated 15 files` |
| R5 | API starts | `./run_rescreen.sh api`, then `curl 127.0.0.1:8765/api/health` | HTTP 200, `status ok`, `rescreen-contract/1.0`, `grok_live false` |
| R6 | Streamlit check view starts | `./run_rescreen.sh ui`, then `curl 127.0.0.1:8502/_stcore/health` | `ok`; page returns HTTP 200 |
| R7 | Milestone 1 intact | part of `release` | `sha256sum -c verification_rescreen/milestone1_expected_sha256.txt` reports all 3 OK |

## Acceptance checks (R2) and what the dashboard must show

| Step | Action | Expected state / events |
|---|---|---|
| 1 | Reset (V1) | Alerts RESCREEN-A and RESCREEN-B, both `OPEN`, against FICT-UK-SL / DEMO-WL-410 |
| 1 | V1 scores, A | Name-only 100 `LINK`; Splink P=0.4493 `REVIEW`; guard `REVIEW` (verified full DOB contradiction) |
| 1 | V1 scores, B | Name-only 91.67 `LINK`; Splink 0.0528 `NO_LINK`; guard flags the contradiction |
| 2 | ana.analyst proposes A, basis `verified_identifier_conflict` (EV-b1e7363003d3 vs EV-93156134c0a3) | Proposal recorded; A `IN_REVIEW` |
| 2 | An analyst tries to approve | 403 `ROLE_NOT_ALLOWED` |
| 2 | rio.senior approves A | A `RESOLVED`; decision `CURRENT` |
| 2 | sam.analyst proposes B, basis `verified_full_dob_conflict` (EV-bc3a528f805f vs EV-de2c9c7efc6f); sam tries to approve | 403 `ROLE_NOT_ALLOWED` |
| 2 | kai.senior approves B | B `RESOLVED`; decision `CURRENT` |
| 3 | Load UK V2 | `ACTIVATED SNAP-FICT-UK-SL-V2-50c30ade`; diff: DEMO-WL-410 amended (`aliases`, `dob`); job `list_change` with `basis_holds 1`, `reopened 1` |
| 3 | A after V2 | `RESOLVED`; approval still `CURRENT`; event `APPROVAL_BASIS_HOLDS` |
| 3 | B after V2 | `OPEN`; `reopen_count 1`; disposition `REOPENED_NEEDS_HUMAN_REVIEW`; old approval `INVALIDATED` (kept); reason `BASIS_NO_LONGER_HOLDS – DOBs now agree (1991-06-14)`; changed fields `list_entry.alias`, `list_entry.dob`; owner sam.analyst; Splink P≈0.99999 via the documented alias "Chan Wai Mun" |
| 4 | Load V2 again, manual rescreen, then daily sweep | `NO_UPDATE`; still exactly 1 `REOPENED` event and exactly 2 alerts |
| 5 | Simulate feed failure (malformed V3) | `FAILED_VALIDATION`; active snapshot stays V2; coverage `DEGRADED: serving last-good …`; sweep still runs |
| 6 | A job fails, then is retried | Failed job recorded; retry completes; event count unchanged (14 → 14) |
| 7 | Material KYC change on A (alias) | `kyc_change` job scoped to A only; A stays `RESOLVED` |
| 8 | Challenger | Live `available:false`; the replay is labelled `REPLAY …`, stored with `is_replay:true`, and kept separate from the human AMEND |
| 8 | Re-close B on the old DOB basis | 409 `BASIS_INVALID` |
| 8 | Request evidence on B | `AWAITING_EVIDENCE` |
| 8 | Reviews | Pending = [RESCREEN-B]; completed = A `APPROVED CURRENT` and B `APPROVED INVALIDATED` |
| 9 | A senior approves their own proposal (scratch DB) | 403 `SELF_APPROVAL_FORBIDDEN` |

## Other checks covered by pytest (`tests_rescreen/`)

- **No label leak:** labels live only in `rescreen_qa/labels.json` (and `evaluation/labels.json`). No export contains label keys or values. `rescreen` never imports `rescreen_qa`, checked both by AST and in a subprocess.
- **Challenger handoff:** contains only `changed_fields`, `approval_basis`, `evidence_ids` and `requested_output`. No state, disposition or verdict.
- **Determinism:** two acceptance runs produce identical exports.
- **HTTP API end to end:** reset, V2, reopen, and the 403 on self-approval.
- **UI smoke test:** Streamlit renders both cases without exceptions.

## UK / US / Mainland China evidence view (`jurisdictions_*.json`, `/jurisdictions?primary=`)

**RESCREEN-B, primary UK:**

| Row | Status | Detail |
|---|---|---|
| UK | `HIT` | Fictional measure UK-FM-12 against DEMO-WL-410 |
| US | `NO_HIT_COMPLETE` | |
| CN | `NO_HIT_COMPLETE` | |

- Both no-hit rows also show `LIST_DIFFERENCE`, meaning the entry is on one list and not on the others. This is shown as a difference, not as clearance.
- `potential_conflict` is `POTENTIAL_CONFLICT_ROUTE_TO_LEGAL`: the fictional CN-FM-07 measure targets the UK listing, and the case has a FICT-BANK-SH nexus.
- With primary CN, the rows reorder to CN, UK, US and the default queue is "Legal (potential conflict)".

**RESCREEN-A:** UK nexus only, so the conflict status is `NOT_ESTABLISHED`.

Every row carries source, snapshot, coverage, the identity evidence classification (supporting / conflicting / missing per field), measure evidence IDs, factual nexus and applicability. The view states that the measures are fictional and that it is not legal advice.

## Known gaps (not defects)

- There are only two customers, so there is no third customer showing a brand-new alert from the V2 alias. B already alerted in V1 on name-only.
- Roles are seeded for a simulated sign-in. There is no authentication and no entity-scoped redaction.
- The Challenger replay text was written by the builder as a labelled sample. It was not produced by Grok.
- QA replay covers milestone cases #03 and #08 plus the two rescreen pairs, not all ten BRD scenarios.
- Not built: the passport scenario and the UK reporting draft (both optional).
- Feed activation is strict: one rejected entry rejects the whole snapshot.
- There is no scheduler; cron calls `./run_rescreen.sh sweep`.
- Timestamps come from the simulated clock.
- A missing body field on a POST returns 404 instead of 400.
