"use client";

import { useState, type FormEvent } from "react";
import { createBrowserClient } from "@supabase/ssr";

export default function RecoveryForm({ settings }: { settings: { url: string; key: string } }) {
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState("");
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const email = new FormData(event.currentTarget).get("email");
    if (typeof email !== "string" || !email.trim()) return;
    setPending(true); setMessage("");
    try {
      const client = createBrowserClient(settings.url, settings.key);
      const { error } = await client.auth.resetPasswordForEmail(email.trim(), { redirectTo: `${window.location.origin}/auth/callback` });
      setMessage(error ? error.code === "over_email_send_rate_limit" || error.code === "over_request_rate_limit"
        ? "Supabase’s email sending limit has been reached. Wait for the limit to reset before requesting another link. Your existing invitation may still work."
        : "Could not request a link right now. Please wait a minute and try again."
        : "If this email has an account, a password setup link is on its way. Check your inbox and junk folder, then open it in this browser.");
    } catch { setMessage("Could not connect. Please try again."); }
    finally { setPending(false); }
  }
  return <form className="login-form" onSubmit={submit}>
    <label>Account email<input name="email" type="email" autoComplete="username" required maxLength={254}/></label>
    <button className="primary" disabled={pending}>{pending ? "Requesting link…" : "Send password setup link"}</button>
    {message && <p className="auth-help" role="status">{message}</p>}
  </form>;
}
