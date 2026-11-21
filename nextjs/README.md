## Identity review workspace

In local demo mode the default view is Identity review. From the repository root run `python3 system/export_dashboard.py /path/to/screening/dev output`, then start or refresh this dashboard. The server reads the ignored local snapshot from `../output/screening-dashboard.local.json`. It does not bundle raw participant data into source code. In Supabase mode the existing authenticated workflow remains the entry point.

The new workspace displays decision counts per hit, alert clearance only when every hit differs, resolved customer and listed-subject facts, all ambiguous candidate pictures, linkage records, reason codes and evidence gaps. Search includes IDs, reason text and evidence IDs. Import validates JSONL fields, decision/reason compatibility and duplicate hits; imported predictions stay in page memory and do not overwrite the saved run. Predictions alone do not contain the source evidence trace. Export downloads the active results.

When a local participant snapshot is available, Screening queue uses the same current run as Identity review, groups its hits into alerts, and supports open/clear status filtering, customer-name search and per-hit evidence inspection. Its source banner records the snapshot generation time in London time. Regenerate the snapshot with the exporter and reload the page after changing the supplied data. Without a participant snapshot the queue retains the synthetic case exercise. Authenticated Supabase queues continue to load their scoped cases. Reviews, Watchlists, V2 rescreen demo and FEBRL benchmark remain separate exercises.

# Wrong John Smith Defender

## Deploy to Netlify

Connect the repository to Netlify and use the root `netlify.toml`. It sets the
base directory to `nextjs`, build command to `npm run build`, publish directory
to `.next` (relative to the base), and Node.js to 22. Netlify automatically adds
its current Next.js adapter for server rendering, API routes and Server Actions.
Do not deploy the repository ZIP or `.next` as a static drag-and-drop site; this
app requires the Next.js runtime. Do not add a single-page-app `/* /index.html`
rewrite.

For authenticated hosting, add these environment variables in the Netlify
project with both build and Functions scopes, then redeploy:

- `DEFENDER_MODE=supabase`
- `SUPABASE_URL`: the project's HTTPS API URL
- `SUPABASE_PUBLISHABLE_KEY`: its `sb_publishable_...` key
- `TAVILY_API_KEY`: optional, for research features

Local `.env.local` values are not uploaded by Git. Apply the migrations in
`supabase/migrations/` in order and assign analyst profiles before testing cloud
access. Set the Supabase Site URL to the deployed HTTPS origin and allow its
`/auth/callback` URL for invitations and password recovery. Without
`DEFENDER_MODE=supabase`, the site opens the synthetic demo; the ignored local
participant snapshot is not included in deployment.

After pushing the configuration, trigger a new deploy and check its build log.
Verify `/login`, a signed-out redirect from `/`, sign-in, and a permitted queue
read. If deployment fails, retain the first error and the resolved build settings
from the log. A successful local build alone does not verify Netlify packaging
or the production Supabase settings.

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

## Supabase login and invitation setup

With `DEFENDER_MODE=supabase`, `/` requires a verified Supabase session. Sign in
at `/login`; the assigned `analyst_profiles` row selects the booking entity and
Junior (`analyst`) or Senior (`reviewer`) workspace. Roles are never selected or
written by the login form. Case and note access continues to use database RLS.

First-time users open the Supabase invitation email and set their own password
at `/account/set-password`. The app accepts the default Supabase fragment link,
PKCE links at `/auth/callback`, and token-hash email templates at `/auth/confirm`.
Credentials from fragment links are removed from browser history before
navigation. Passwords are sent only to the authenticated Supabase update flow;
the application does not store them in its own database.

For recovery, use `/login/forgot-password`. In Supabase Authentication → URL
Configuration, allow the exact callback URLs for each running app origin, e.g.
`http://127.0.0.1:3000/auth/callback` and
`http://localhost:3000/auth/callback` (configured for this local project). Use the
same browser and host when requesting and opening PKCE recovery links. Add the
production HTTPS callback when deploying; no hosted deployment is included here.
Email send limits are reported in the UI; wait for the limit to reset rather
than repeatedly requesting a link. Never disable email verification to bypass it.

Authentication verification:
`npm test -- tests/auth.test.ts` and
`node --experimental-strip-types --test tests/auth-validation.test.mjs`.

### Senior access across booking entities

Migration `202611210004_senior_scope.sql` adds `analyst_profiles.data_scope`.
Existing profiles default to `entity`. An administrator may explicitly assign
`review_role = 'reviewer'` and `data_scope = 'all'` to a Senior who needs access
to both UK and US cases, review history and notes. The database rejects `all`
scope for Junior profiles. The required `booking_entity` remains the account's
administrative home; it does not restrict an explicitly assigned all-data Senior.
RLS remains enabled. Profiles remain administrator-managed, and ordinary clients
cannot grant themselves broader scope. Senior access does not grant database
administration, auth-user management, or deletion of review history.

### Imported screening runs

Migrations `202611210005_screening_imports.sql` and
`202611210006_import_screening_rpc.sql` add durable imported runs and grouped
alerts. The authenticated `/admin/import-screening` page validates the local
`../output/screening-dashboard.local.json` and submits one atomic RPC. A content
hash identifies each import; retries preserve the existing payload and alert
rows. Payloads with the same identifier and different content are rejected.

The Supabase dashboard reads the stored payload, not a local-file fallback.
Screening queue offers Imported alerts and Demo cases separately. Findings,
evidence IDs and identity traces remain unchanged; no human approval, review
history or final closure is inferred from a model/rule result. These imports have
no booking-entity assignment, so only an explicitly all-data Senior can read or
import them. Entity-scoped Junior accounts retain their existing cases. Direct
client writes to import tables remain denied.

The current imported run has 440 alerts, 819 hit findings and 880 traces. It is
the participant development set, not the separate 10,000-record FEBRL4 benchmark.

### Screening risk dashboard

The workspace opens on **Risk dashboard**. It scores the latest assigned screening
run, or the visible demo cases when no participant run is assigned. The dashboard
includes High / Medium / Low counts, risk distribution, open investigation and
closure counts, source coverage, a searchable and paginated risk register, score
explanations, evidence drilldown and a CSV export of every matching row.

`lib/risk.ts` defines the versioned `screening-triage-v1` rules. Scores are
operational priorities, not calibrated probabilities or final compliance findings.
High is 70–100, Medium 35–69, Low 0–34. Identity agreement starts at 75,
unresolved identity at 40, and exclusion at 10. For matching/unresolved hits,
customer ambiguity adds 15, distinct evidence gaps add 5 each (maximum 15),
unavailable traces or unverified customer identity add 10, and absent evidence
IDs add 10. Scores cap at 100. The alert takes its highest hit score, independent
of UI filters; missing evidence never supports exclusion. Case fixtures use the
screening outcome, documented evidence gaps and list-entry review signals as
explained in the dashboard methodology.

Senior closure changes workflow status without reducing the automated score.
Closure counts sync between the risk dashboard and review workspace during the
session; cloud closures reload from the review table. Risk scoring itself needs
no additional database migration. Cloud closure storage still requires migration
`202611210007_screening_review_closure.sql` from the preceding change. Demo
closures remain session-only. No historical risk trend, SLA deadline or transaction
risk is inferred from data the run does not contain.
