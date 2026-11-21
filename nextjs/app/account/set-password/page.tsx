import Link from "next/link";
import { ShieldCheck } from "lucide-react";
import { cloudMode, config, serverClient } from "../../../lib/supabase";
import PasswordForm from "./form";

export const dynamic = "force-dynamic";
export default async function SetPasswordPage() {
  const settings = cloudMode ? config() : null;
  const client = settings ? await serverClient(settings) : null;
  const auth = client ? await client.auth.getUser() : null;
  return <main className="login-shell"><section className="login-card">
    <div className="brand-emblem"><ShieldCheck size={22}/></div>
    <h1>Set your password</h1><p>Finish your invitation or reset your analyst account password.</p>
    {auth?.data.user ? <><p className="auth-help">Account: <strong>{auth.data.user.email}</strong></p><PasswordForm/></> : <p className="auth-help" role="status">Open the secure link in your invitation or password email first. If it has expired, request a new link.</p>}
    <Link className="auth-back" href="/login/forgot-password">Request a new setup link</Link>
    <Link className="auth-back" href="/login">Back to sign in</Link>
  </section></main>;
}
