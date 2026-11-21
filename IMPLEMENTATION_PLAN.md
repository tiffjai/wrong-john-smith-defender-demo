# Brief v3 implementation plan

## Objective
Pivot the default experience from sanctions case dispositions to per-hit entity resolution: DIFFERENT_ENTITY, SAME_ENTITY or REVIEW. Resolve the bank customer before comparing with the listed subject. Keep previous dashboard features available as legacy exercises.

## Implementation
1. Add a standard-library Python executable `system/run <data folder> <output file>`. Read only the supplied folder, require POLICY.md, join account/login/email to CRM and onboarding to passed KYC, preserve exact evidence IDs, and emit deterministic JSONL. Ambiguous people, rejected checks, conflicting verified facts and missing evidence remain review cases.
2. Keep policy numbers and reason codes in an explicit data-folder adapter, rather than guessing the unavailable bank SOP. Without that adapter, return conservative REVIEW outputs using a review code present in POLICY.md; never auto-clear based on a guessed threshold. Explain this baseline limitation.
3. Add a default entity-resolution dashboard with per-alert aggregation, per-hit decisions, customer/watchlist evidence, linkage paths, reason codes and local prediction import/export. Label demonstration records as synthetic. Keep compliance dispositions separate from identity outcomes.
4. Verify partial dates, evidence precedence, ambiguity, deterministic output, multi-hit alert closure and import validation. Run existing regression checks, typecheck and production build.

## Dataset received
The user supplied `/Users/wing/Downloads/screening/`. Read its actual POLICY.md, JSONL schemas and validator. Implemented the bank SOP in `system/bank_resolver.py`; the provisional adapter is confined to the separate synthetic example path. The real dataset stays in Downloads. Generated `output/dev.jsonl` and a local dashboard snapshot are ignored by Git. PDF submission instructions do not authorize publication.

## Verification
- 819 predictions for 440 development alerts; organizer validator reports zero problems.
- Practice: 50/50 correct decisions, zero unsafe clearances, decision score 100; reason-code agreement 98%, customer-record agreement 100%. These are development results, not unseen-set performance.
- Corrected general age/money, Unicode legal-name, successful KYC-note and country parsing issues exposed during evaluation; no practice IDs or labels are used by the runner.
- Python and frontend regression tests, typecheck and build; browser checks cover matching, ambiguity, sibling-hit navigation and filtering.
- Existing uncommitted project changes and earlier dashboard exercises retained.

## Acceptance
- Exactly one result per alert/hit pair, with the seven requested fields.
- Missing/partial dates do not become invented mismatches; rejected KYC is ignored.
- Several distinct CRM candidates are AMBIGUOUS rather than selected by order.
- An alert closes only when every hit is DIFFERENT_ENTITY.
- Synthetic examples exercise all three outcomes and joined KYC provenance.
- Imports stay in browser memory and are clearly distinct from the synthetic examples.
