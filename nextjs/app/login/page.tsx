import { redirect } from "next/navigation";
import { ShieldCheck } from "lucide-react";
import { cloudMode, config, serverClient } from "../../lib/supabase";
import SignInForm from "./form";

export const dynamic = "force-dynamic";

export default async function Login() {
  if (!cloudMode) redirect("/");
  const settings = config();
  if (settings) {
    const supabase = await serverClient(settings);
    const { data } = await supabase.auth.getClaims();
    if (data?.claims.sub) redirect("/");
  }
  return <main className="login-shell"><section className="login-card">
    <div className="brand-emblem"><ShieldCheck size={22} /></div>
    <h1>Analyst sign-in</h1><p>Use your assigned Supabase demo account.</p>
    {settings ? <SignInForm /> : <p role="alert">Supabase project settings are missing.</p>}
  </section></main>;
}
