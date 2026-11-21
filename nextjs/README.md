## Brief v3 entity-resolution workspace

In local demo mode the default view is Entity resolution. From the repository root run `python3 system/export_dashboard.py /path/to/screening/dev output`, then start or refresh this dashboard. The server reads the ignored local snapshot from `../output/screening-dashboard.local.json`. It does not bundle raw participant data into source code. In Supabase mode the existing authenticated workflow remains the entry point.

The new workspace displays decision counts per hit, alert clearance only when every hit differs, resolved customer and listed-subject facts, all ambiguous candidate pictures, linkage records, reason codes and evidence gaps. Search includes IDs, reason text and evidence IDs. Import validates JSONL fields, decision/reason compatibility and duplicate hits; imported predictions stay in page memory and do not overwrite the saved run. Predictions alone do not contain the source evidence trace. Export downloads the active results.

The existing Screening queue, Reviews, Watchlists, V2 rescreen demo and FEBRL benchmark remain separate exercises; their counts and dispositions are not combined with the Brief v3 run.

# Wrong John Smith Defender

## Run the local app

Use Node.js 22 or later. From this directory:

```sh
npm ci
npm run dev -- --hostname 127.0.0.1
```

Open `http://127.0.0.1:3000`. The default is the offline demo. Start with CASE-11 for ownership review, then open CASE-12 to compare replacement history, overlapping validity and the cross-customer document-key conflict. CASE-08 and CASE-01 show the original Builder evidence and scores. Use Load V2 to surface CASE-03. The V2 control replays a local fixture and review history is stored in this browser for the offline demo.

The Reviews tab moves a case from Unprocessed to Processed after the first human decision. An escalation or evidence request stays visible as the latest decision. CASE-11 preserves the original Challenger JSON as a labelled replay, separate from human decisions.

CASE-08 lists the fictional watchlist by name and shows its entry ID, linked record, historical listing, explicit removal and the last successful snapshot check. The stale-feed control keeps the last observed result visible while marking current status unconfirmed. UK format reference: [UK Sanctions List format guide](https://www.gov.uk/guidance/format-guide-for-the-uk-sanctions-list).

## Tavily research

The case detail panel includes three on-demand research functions:

1. **Official-source checks:** Tavily Search restricted to UK government/company registry, US Treasury/OFAC, UN and EU Council domains. Use this to find public sanctions notices and registry leads for ownership review.
2. **Recent adverse media:** Tavily Search with the news topic, past-month filter and risk terms (sanctions, fraud, corruption, investigation, money laundering). Add public geographic or company context to distinguish namesakes.
3. **Source extraction:** Tavily Extract retrieves text from a selected search result or public HTTPS URL for inspection and citation.

Add `TAVILY_API_KEY` to `.env.local` and restart the server. The key stays on the server. No requests run until the analyst clicks a research button. Submitted search terms and URLs go to Tavily; avoid confidential identifiers. Without a key the panel gives setup instructions and the existing demo remains available. Live requests consume your Tavily credits.

The localhost demo permits research for bundled cases. Hosted deployments require `DEFENDER_MODE=supabase`; the route checks sign-in and case access using the existing row-level security policy. Same-origin requests are required. Run a single check with the UI, inspect citations, extract a result, then export the research JSON. Test unavailable-key feedback by leaving the setting blank.

Each run records the case, action, actual query, retrieval timestamp, provider request ID, source URL, published date when supplied, excerpt/text and content-derived evidence identifiers. Extraction failures and empty results are explicit. Plain text rendering treats remote content as untrusted. Export retains the latest ten runs in the current case view; research is not persisted into Supabase or merged into the original evidence packet. Switching cases clears the panel.

These are research leads for human verification. A namesake result is not an identity match; search snippets do not establish current list status, ownership percentages or legal conclusions. No results is not clearance. Retrieval timestamps do not prove source freshness. Research never changes matcher scores, listing snapshots, rescreen state or review decisions.

Validation: `npm run test:research`, `npm run typecheck`, `npm run build`. Unit tests mock the provider and consume no credits. A configured API key is required to verify live responses.

References: [Tavily Search](https://docs.tavily.com/documentation/api-reference/endpoint/search), [Tavily Extract](https://docs.tavily.com/documentation/api-reference/endpoint/extract). Search and Extract are the closest fit for targeted case research; broad site crawling adds collection volume without resolving namesake ambiguity.

## Two-closure V2 exercise

Open **V2 rescreen demo** in offline mode. As **Demo analyst**, propose a closure for each customer and cite the evidence shown. Switch to **Demo senior reviewer**, then approve each proposal. Open **Watchlists**. **Load V2** changes the loaded snapshot and leaves the screened version on V1. **Rescreen** is a separate manual step: A keeps the independently verified registry exclusion, and B returns to human review because the V1 DOB conflict used in its original approval has disappeared. Load V2 again or press Rescreen again and check that B reopens only once. The retrieval threshold filters normalised name and alias similarity. That score is separate from the Splink identity probability. Download the audit report for both cases. With B selected, export the Challenger packet, or request evidence or escalate as the analyst.

The exercise is a synthetic browser-local demo for two enrolled customers. It does not connect to an official feed, it does not screen the bank automatically, and it does not store this rehearsal in Supabase. The existing Supabase queue has its own sign-in and review policies. Refresh the Splink outputs with `npm run rescreen:scores`. `npm test` runs the rescreen regression tests.

`npm run typecheck` and `npm run build` verify the application. It runs offline after dependencies are installed. The UI uses no account when `DEFENDER_MODE=demo`.

## Reproduce the FEBRL4 benchmark

```sh
npm run benchmark
```

Install `uv` first. The script fetches the two pinned synthetic CSVs from the upstream Record Linkage Toolkit, runs Splink and RapidFuzz over one candidate set, and overwrites `data/benchmark.json`. The generated result includes package versions, source SHA-256 hashes, thresholds, blocking rules and examples. It keeps label-bearing upstream identifiers and `soc_sec_id` out of scoring. DOB verification is unknown in FEBRL4. Use the separate synthetic screening cases to evaluate the verified-DOB guard.

The fixed comparison weights are a documented demo configuration. Evaluate threshold changes on a separate dataset before making claims about generalisation. The OpenSanctions data dictionary is a reference for watchlist fields and provenance. The app imports the fictional case packets we ship.

## Supabase kickoff

1. Use the team’s approved synthetic demo project. Get its API URL and publishable key from Connect in the Supabase dashboard. Copy `.env.example` to `.env.local`, set `DEFENDER_MODE=supabase`, and fill in `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY`. The app’s authenticated mode requires both settings and validates the new-style `sb_publishable_` key. Restart Next.js after changing them.
2. Have a project admin apply `supabase/migrations/202611210001_defender_demo.sql` once with the project migration workflow or SQL Editor. Use `node scripts/seed.mjs > /tmp/defender-demo-seed.sql` and apply the generated synthetic seed in SQL Editor. It can be reapplied without duplicating cases. Existing synthetic CASE-08 records receive the listing history if it is missing.
3. Have a project admin create two confirmed demo accounts in Authentication → Users, then use their user UUIDs in `public.analyst_profiles`. Assign a UK `reviewer` and a US `analyst`. That profile assignment stays under project administrator control.

```sql
insert into public.analyst_profiles (user_id, booking_entity, review_role)
values
  ('<UK reviewer UUID>', 'UK', 'reviewer'),
  ('<US analyst UUID>', 'US', 'analyst');
```

4. Verify signed-out redirects, signed-out review API rejection, sign-in, refresh and sign-out. The UK reviewer sees CASE-03, CASE-08, CASE-11 and CASE-12, and can resolve an in-scope case. The US analyst sees CASE-01 and can submit or escalate an in-scope case. Save a permitted review, reload the page and inspect history. Verify a cross-entity write and an analyst resolve are rejected by RLS even on a direct request. Record observed responses for DefenderQA.

The cloud page loads its queue from Supabase under the signed-in account. It reports missing setup and fetch failures explicitly. Keep the existing offline demo process available while the team verifies the cloud project.

- [Supabase Next.js server-side auth](https://supabase.com/docs/guides/auth/server-side/creating-a-client?framework=nextjs)
- [Supabase row-level security](https://supabase.com/docs/guides/database/postgres/row-level-security)
- [FEBRL4 data documentation](https://recordlinkage.readthedocs.io/en/stable/ref-datasets.html#febrl-datasets)
- [OpenSanctions data dictionary](https://www.opensanctions.org/reference/)
