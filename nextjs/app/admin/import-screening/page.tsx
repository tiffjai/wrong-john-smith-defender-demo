import { readFile } from "node:fs/promises";
import path from "node:path";
import { redirect } from "next/navigation";
import { cloudMode, config, serverClient } from "../../../lib/supabase";
import { hasAllDataAccess } from "../../../lib/access-scope";
import { prepareScreeningImport } from "../../../lib/screening-import";
import ImportForm from "./form";

export const dynamic = "force-dynamic";
export default async function ImportScreening() {
  const settings = cloudMode ? config() : null;
  if (!settings) return <main className="login-shell">Supabase configuration required.</main>;
  const client = await serverClient(settings);
  const { data } = await client.auth.getUser();
  if (!data.user) redirect("/login");
  const profile = await client.from("analyst_profiles").select("*").eq("user_id", data.user.id).maybeSingle();
  if (!hasAllDataAccess(profile.data ?? undefined)) return <main className="login-shell">All-data Senior access required.</main>;
  const run = JSON.parse(await readFile(path.resolve(process.cwd(), "../output/screening-dashboard.local.json"), "utf8"));
  const prepared = prepareScreeningImport(run);
  return <main className="workspace"><h1>Screening import preparation</h1>
    <p>{prepared.alerts} alerts · {prepared.hits} findings · Ready for transactional import.</p>
    <p>Import the validated run into Supabase. Rerunning adds no duplicates. Unassigned data remains restricted to all-data Seniors. Findings are not human approvals.</p>
    <ImportForm/>
  </main>;
}
