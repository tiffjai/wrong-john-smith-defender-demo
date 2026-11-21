import { redirect } from "next/navigation";
import { ShieldCheck } from "lucide-react";
import benchmark from "../data/benchmark.json";
import { demoNotes, fixtures } from "../lib/fixtures";
import { cloudMode, config, serverClient } from "../lib/supabase";
import type { Case, CaseNote, Review } from "../lib/types";
import Dashboard from "./dashboard";

export const dynamic = "force-dynamic";

function ConnectionMessage({ title, detail }: { title: string; detail: string }) {
  return <main className="login-shell"><section className="login-card">
    <div className="brand-emblem"><ShieldCheck size={22} /></div>
    <h1>{title}</h1><p>{detail}</p>
  </section></main>;
}

export default async function Page() {
  if (!cloudMode) return <Dashboard mode="demo" cases={fixtures} benchmark={benchmark} reviews={[]} notes={demoNotes} />;

  const settings = config();
  if (!settings) return <ConnectionMessage title="Supabase setup required"
    detail="Set the project URL and publishable key in .env.local, then restart Next.js." />;

  const supabase = await serverClient(settings);
  const { data: auth } = await supabase.auth.getClaims();
  const viewerId = auth?.claims.sub;
  if (!viewerId) redirect("/login");

  const [profile, cases, reviews, notes] = await Promise.all([
    supabase.from("analyst_profiles").select("booking_entity, review_role").eq("user_id", viewerId).maybeSingle(),
    supabase.from("screening_cases").select("id, title, booking_entity, snapshot, packet, recommendation").order("id", { ascending: false }),
    supabase.from("review_events").select("case_id, decision, rationale, created_at").order("created_at", { ascending: false }),
    supabase.from("case_notes").select("id, case_id, author_id, body, created_at").order("created_at", { ascending: false }),
  ]);
  if (profile.error || cases.error || reviews.error || notes.error) return <ConnectionMessage title="Could not load the screening queue"
    detail="Check the Supabase connection and apply the project migrations before trying again." />;
  if (!profile.data) return <ConnectionMessage title="Booking entity assignment required"
    detail="A project administrator can assign this demo account to an analyst profile in Supabase." />;

  return <Dashboard mode="supabase" cases={cases.data as Case[]} benchmark={benchmark}
    reviews={reviews.data as Review[]} notes={(notes.data ?? []) as CaseNote[]} viewerId={viewerId} profile={profile.data} />;
}
