import Link from "next/link";
import { ShieldCheck } from "lucide-react";
import { cloudMode, config } from "../../../lib/supabase";
import RecoveryForm from "./form";

export const dynamic = "force-dynamic";
export default function ForgotPasswordPage() {
  const settings = cloudMode ? config() : null;
  return <main className="login-shell"><section className="login-card">
    <div className="brand-emblem"><ShieldCheck size={22}/></div>
    <h1>Set up or reset your password</h1><p>Use the email address invited to Defender. Access is managed by your administrator.</p>
    {settings ? <RecoveryForm settings={settings}/> : <p role="alert">Supabase authentication is not configured.</p>}
    <Link className="auth-back" href="/login">Back to sign in</Link>
  </section></main>;
}
