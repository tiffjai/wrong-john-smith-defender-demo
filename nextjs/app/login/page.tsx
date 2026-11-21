import { redirect } from "next/navigation";
import { ShieldCheck } from "lucide-react";
import { cloudMode, config, serverClient } from "../../lib/supabase";
import SignInForm from "./form";
import Link from "next/link";

export const dynamic = "force-dynamic";

export default async function Login({ searchParams }: { searchParams: Promise<{ error?: string }> }) {
  if (!cloudMode) redirect("/");
  const settings = config();
  const error = (await searchParams).error;
  if (settings) {
    const supabase = await serverClient(settings);
    const { data } = await supabase.auth.getClaims();
    if (data?.claims.sub) redirect("/");
  }
  return <main className="login-shell"><section className="login-card">
    <div className="brand-emblem"><ShieldCheck size={22} /></div>
    <span className="auth-eyebrow">Defender · Secure workspace</span>
    <h1>Welcome back</h1><p>Sign in to your assigned analyst workspace.</p>
    <div className="auth-roles"><span>Junior · Investigate & escalate</span><span>Senior · Review & close</span></div>
    {error === "link" && <p className="error" role="alert">This email link is invalid or has expired. Request a new password setup link below.</p>}
    {settings ? <SignInForm /> : <p role="alert">Supabase project settings are missing.</p>}
    <Link className="auth-back" href="/login/forgot-password">First login or forgot your password?</Link>
    <p className="auth-help">Your booking entity and role come from your Supabase profile. Contact the administrator if access has not been assigned.</p>
  </section></main>;
}
