---
name: defender-evidence-review
description: Review one synthetic screening packet and return an evidence-cited JSON recommendation for a human analyst.
---

# Defender evidence review

1. Use the supplied synthetic packet. Cite its IDs for every finding. Missing fields are unknown. Check original-script names and aliases, date precision, source dates and reliability, shared addresses and common-source copies.
2. Inspect both edges of an A–B–C chain and compare A and C from their raw evidence. Flag conflicting verified full DOBs. Preserve plausible candidates supported by a documented alias. Check for a specific fictional measure and factual nexus before recommending cross-border review. A completed list difference by itself is not a conflict.
3. Return a single raw JSON object with case_id, evidence_ids, contradictions, missing_evidence, suggested_next_check and review_priority. Use arrays for evidence_ids and for findings, and include finding and evidence_ids within each contradiction or missing-evidence item. Cite the record for the next check where possible. Priority is high for a verified material conflict, medium for material ambiguity, or low otherwise. Leave disposition to the designated human reviewer.
