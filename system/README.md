# Same Person or Not? — deterministic screening system

Run from the repository root, with Python 3.9 or newer and no packages:

```sh
system/run /path/to/screening/dev output/dev.jsonl
python3 /path/to/screening/validate.py --data /path/to/screening/dev --output output/dev.jsonl --score /path/to/screening/dev/practice_labels.jsonl
python3 system/export_dashboard.py /path/to/screening/dev output
```

The exporter regenerates the same predictions plus `output/screening-dashboard.local.json`. Start the Next.js dashboard with `cd nextjs && npm run dev -- --hostname 127.0.0.1`; Entity resolution opens by default in local demo mode. Refresh after regenerating the snapshot. A clean checkout without participant data shows synthetic examples. Supabase mode retains the existing authenticated case workflow and never loads this local dataset.

## Architecture

```text
alerts → account/login/email → CRM person candidates
                                  ↓
                 union by phone + full DOB / approved document
                                  ↓
           accounts → onboarding applicant → approved KYC
                    email → onboarding and support notes
                                  ↓
                       latest verified person picture
                                  ↕
hit → structured dates / first-paragraph age / scoped search results
                                  ↓
               SOP contradictions → agreements → REVIEW
                                  ↓
                one JSONL row per hit + exact evidence IDs
```

`bank_resolver.py` implements the supplied bank identity SOP. It indexes source systems, groups records transitively by the SOP's person links, and disambiguates joint-account or search candidates using screened details. Multiple distinct people are compared independently; unanimous decisions retain `AMBIGUOUS`, while disagreement returns `AMBIGUOUS_CUSTOMER_RECORD`. It does not read `practice_labels.jsonl`. Practice labels are used only by the organizer's separate validator.

Approved KYC and recognised successful onboarding notes outrank declared fields; the most recent approved evidence supplies the name and DOB. Rejected or expired checks do not supply identity facts. Country sets include residence, nationality, approved document countries and recognised historical residence notes across the person's linked records. This is identity resolution, not a sanctions-policy engine.

The watchlist resolver uses all structured dates, then first-paragraph age evidence if dates are absent, then provided search results only when the listing phrase and hit country agree. Age evidence preserves both possible years. Only the SOP's English `According to …; Month DD, YYYY:` reports count for temporal exclusion. Country codes, nationalities, accents, initial-only names, supplied name variants, together/apart names and edit-distance rules are normalised deterministically. A one-year birth-year gap alone neither confirms nor excludes. Missing date components stay missing.

Decisions carry the seven required fields, reason codes and exact source IDs. The optional local dashboard snapshot separately records the two identities, linkage IDs, missing evidence and the policy file hash. It is not part of the submitted JSONL contract. An alert is clear only when all its hits are `DIFFERENT_ENTITY`.

## Three illustrative cases

These examples are invented; the implementation does not contain dataset-specific IDs or answers.

- **Clear mismatch:** an approved check gives 14 March 1988; the hit gives birth year 1952. Every listed date contradicts the customer beyond the one-year tolerance, so `DOB_MISMATCH` clears the hit. Cite the customer, approved check and hit.
- **Match:** the verified name and full DOB agree with one hit name and date, and there is no location or other identity contradiction. `NAME_DOB_MATCH` retains the alert; a common country permits `NAME_DOB_LOCATION_MATCH`.
- **Review:** the customer and hit share a name but the hit has no usable DOB or location. `INSUFFICIENT_DATA` keeps the hit open. A second cleared hit in the same alert does not close it.

## Reproducibility, runtime and cost

No language model, prompts, network, API keys, random sampling or system-clock-dependent decisions are used. The runner reads the supplied data folder, sorts output by alert and hit, and writes JSON with stable key order. Only code and the supplied folder are needed. The standalone contract is exactly `system/run <data folder> <output file>`.

The supplied development set has 440 alerts and 819 hits. Local runs take roughly 7–14 seconds with zero model/API cost. Five separate full-dataset process runs are checked for byte-identical output. Organizer validation reports 819 rows and zero format/evidence-ID problems. Practice evaluation: 50/50 correct decisions, zero unsafe clearances, decision score 100, reason-code agreement 100%, customer record agreement 100%. This is a development measurement after parser iteration, not independent unseen-set validation or a full reasons score.

## Limits

The engine implements the supplied SOP, not an arbitrary new policy interpreter. Country aliases and free-text parsing are finite rule sets. Unrecognised note wording, ambiguous date formats and indirect search-name variants can leave facts unresolved. Search retrieval uses normalised token-sorted query names; it does not perform live internet searches. Evidence IDs validate structurally, but a human still needs to assess completeness and whether each citation is decisive. No unseen-set performance is claimed.

`resolver.py` also retains a small explicit-policy-adapter path for the invented `system/examples/` data. That path is used only when `name_variants.json` is absent and must not be confused with the bank SOP implementation.

## Tests and participant data

```sh
python3 -m unittest discover -s system/tests -v
cd nextjs
npm run typecheck
npm test
node --experimental-strip-types --test tests/*.test.mjs
npm run build
```

Keep the participant dataset outside this repository. Generated participant predictions, raw participant data and detailed dashboard snapshots are ignored by Git. Generate `output/dev.jsonl` locally for the event submission. The dataset stays in its supplied folder; only local derived artifacts are written. No upload, publication, submission, deployment or API call is performed by these commands.
