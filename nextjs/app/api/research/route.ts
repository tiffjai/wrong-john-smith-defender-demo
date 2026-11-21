import { cloudMode, config, serverClient } from "../../../lib/supabase";
import { fixtures } from "../../../lib/fixtures";
import { publicUrl, research, ResearchError } from "../../../lib/tavily";
import { isSameOrigin, requestOrigin } from "../../../lib/request-origin";

export async function POST(request: Request) {
  if (!isSameOrigin(request)) return Response.json({ error: "Same-origin research requests required. Open the dashboard and run the search from this page." }, { status: 403 });
  const input = await request.json().catch(() => null);
  if (!input || typeof input.case_id !== "string" || !/^CASE-\d{2}$/.test(input.case_id) ||
    !["official", "news", "extract", "photos"].includes(input.action) || typeof input.query !== "string" ||
    input.query.trim().length < 2 || input.query.length > 400 || (input.action === "extract" && !publicUrl(input.url))) {
    return Response.json({ error: "Choose a research function, enter 2–400 characters and use a public HTTPS source URL for extraction." }, { status: 400 });
  }
  if (cloudMode) {
    const settings = config();
    if (!settings) return Response.json({ error: "Supabase setup required." }, { status: 503 });
    const supabase = await serverClient(settings);
    const { data: auth } = await supabase.auth.getClaims();
    if (!auth?.claims.sub) return Response.json({ error: "Sign in to research this case." }, { status: 401 });
    const { data, error } = await supabase.from("screening_cases").select("id").eq("id", input.case_id).maybeSingle();
    if (error) return Response.json({ error: "Could not verify case access." }, { status: 502 });
    if (!data) return Response.json({ error: "Case unavailable." }, { status: 404 });
  } else {
    // Offline demo must not become an anonymous public proxy for a paid API.
    const host = new URL(requestOrigin(request)!).hostname;
    if (!["localhost", "127.0.0.1", "[::1]"].includes(host)) return Response.json({ error: "Live demo research is available on localhost. Use authenticated Supabase mode when hosted." }, { status: 403 });
    if (!fixtures.some(item => item.id === input.case_id)) return Response.json({ error: "Unknown demo case." }, { status: 404 });
  }
  const key = process.env.TAVILY_API_KEY?.trim();
  if (!key) return Response.json({ error: "Set TAVILY_API_KEY in .env.local and restart Next.js to enable live research." }, { status: 503 });
  try {
    const result = await research({ case_id: input.case_id, action: input.action, query: input.query.trim(), url: publicUrl(input.url) ?? undefined }, key);
    return Response.json(result, { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    return Response.json({ error: error instanceof ResearchError ? error.message : "Research failed. Try again." }, { status: error instanceof ResearchError ? error.status : 502 });
  }
}
