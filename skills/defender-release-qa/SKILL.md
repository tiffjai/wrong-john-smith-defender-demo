---
name: defender-release-qa
description: Independently replay the synthetic Defender suite against a versioned build and recommend whether to hold the demo release.
---

# Defender release QA

1. Identify the artifact or commit, fixture set, snapshot IDs and matcher configuration. Use held-out labelled synthetic cases. Keep labels outside scoring and bot evidence. Compare configurations on a fixed snapshot, then compare list versions on a fixed configuration.
2. Run cases 01–10. Cover conflicting full DOBs, shared address, sourced transliteration, swapped names or typos, partial or placeholder DOB, ambiguous day/month, dated address history, A–B–C endpoint conflict, copied sources and distinct PEP/sanctions records.
3. Verify V2 alias alert, repeat-load deduplication, last-good fallback on feed failure, one manual daily sweep, reopening with history, role scope and escalation, and the no-Grok review path. Confirm the output packet contains stable evidence IDs and excludes QA labels.
4. Report true pairs retrieved / labelled true pairs, missed true matches / labelled true pairs, false positives / labelled non-matches, and manual-review volume / evaluated alerts. Name the scoring, retrieval or routing stage for each miss and report unexecuted checks. Hold a proposed setting that loses a critical true match. Give the team the run command and evidence for its release decision.
