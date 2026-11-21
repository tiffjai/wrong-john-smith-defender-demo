# Same Person or Not? — Defender

Brief v3 entity-resolution system and dashboard. The local dashboard opens on **Identity review**, with per-hit DIFFERENT_ENTITY / SAME_ENTITY / REVIEW outcomes, two-sided identity evidence, ambiguous candidate comparisons, alert aggregation and prediction JSONL import/export.

## Run the system

```sh
system/run /path/to/screening/dev output/dev.jsonl
python3 system/export_dashboard.py /path/to/screening/dev output
cd nextjs
npm ci
npm run dev -- --hostname 127.0.0.1
```

Open [the dashboard](http://127.0.0.1:3000). The exporter supplies local participant results; without it the dashboard shows labelled synthetic examples. The raw dataset stays outside the repository. Generated predictions and detailed local dashboard snapshots stay ignored by Git.

See [system architecture and validation](system/README.md) and the [implementation plan](IMPLEMENTATION_PLAN.md). The organizer's validator is supplied with the dataset. No model or external API is needed.

## Earlier dashboard exercises


The [Grok Supabase builder](bots/README.md) connects a local Grok coding bot to
the hackathon Supabase project. Launch it with `python3 scripts/grok-bot.py`.

Track 3 entity resolution prototype with fictional screening evidence. The [Next.js dashboard](nextjs/README.md) includes the two-customer V1/V2 review exercise, evidence inspection, a matcher benchmark, and a scoped Supabase configuration. The original Streamlit milestone is in `wrong-john-smith-defender/`.

## Start the local dashboard

```sh
cd nextjs
npm ci
npm run dev -- --hostname 127.0.0.1
```

Open `http://127.0.0.1:3000` and select **V2 rescreen demo**. Propose both closures as the demo analyst, then approve both as the demo senior reviewer. On **Watchlists**, load V2 without rescreening, then press **Rescreen**. Customer A stays closed and Customer B reopens once. The exercise uses browser-local rehearsal identities and saves its history in the browser. The separate [Supabase setup](nextjs/README.md#supabase-kickoff) covers authenticated access to the dashboard case queue.

The [kickoff plan](KICKOFF_PLAN.txt) and Grok Bot personas are in the repository root. The two-closure exercise and its reproduction commands are documented in the [dashboard README](nextjs/README.md#two-closure-v2-exercise).
