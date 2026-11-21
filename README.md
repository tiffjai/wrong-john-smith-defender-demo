# Wrong John Smith Defender

Track 3 entity resolution prototype with fictional screening evidence. The [Next.js dashboard](nextjs/README.md) includes the two-customer V1/V2 review exercise, evidence inspection, a matcher benchmark, and a scoped Supabase configuration. The original Streamlit milestone is in `wrong-john-smith-defender/`.

## Start the local dashboard

```sh
cd nextjs
npm ci
npm run dev -- --hostname 127.0.0.1
```

Open `http://127.0.0.1:3000` and select **V2 rescreen demo**. Propose both closures as the demo analyst, then approve both as the demo senior reviewer. Load V2 and verify that Customer A stays closed and Customer B reopens once. The exercise uses browser-local rehearsal identities and saves its history in the browser. The separate [Supabase setup](nextjs/README.md#supabase-kickoff) covers authenticated access to the dashboard case queue.

The [kickoff plan](KICKOFF_PLAN.txt) and Grok Bot personas are in the repository root. The two-closure exercise and its reproduction commands are documented in the [dashboard README](nextjs/README.md#two-closure-v2-exercise).
