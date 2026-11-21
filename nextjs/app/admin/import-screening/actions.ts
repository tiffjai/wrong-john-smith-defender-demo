"use server";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { revalidatePath } from "next/cache";
import { cloudMode, config, serverClient } from "../../../lib/supabase";
import { hasAllDataAccess } from "../../../lib/access-scope";
import { prepareScreeningImport } from "../../../lib/screening-import";

export async function importLatestRun() {
  const settings = cloudMode ? config() : null;
  if (!settings) return "Supabase configuration required.";
  const client = await serverClient(settings);
  const { data } = await client.auth.getUser();
  if (!data.user) return "Sign in before importing.";
  const profile = await client.from("analyst_profiles").select("*").eq("user_id",data.user.id).maybeSingle();
  if (!hasAllDataAccess(profile.data ?? undefined)) return "All-data Senior access required.";
  try {
    const run = JSON.parse(await readFile(path.resolve(process.cwd(),"../output/screening-dashboard.local.json"),"utf8"));
    const prepared = prepareScreeningImport(run);
    const { data: result, error } = await client.rpc("import_screening_run", {p_id: prepared.id,p_payload:run});
    if (error) return "Import could not be completed. Check the import migration and connection; no partial import was saved.";
    revalidatePath("/");
    return `Imported ${result.alerts} alerts and ${result.hits} findings into Supabase. Repeating this import adds no duplicates.`;
  } catch { return "Could not validate or read the local screening run."; }
}
