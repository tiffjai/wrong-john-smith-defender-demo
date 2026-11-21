"use client";
import { useActionState } from "react";
import { setPassword } from "./actions";

export default function PasswordForm() {
  const [error, action, pending] = useActionState(setPassword, "");
  return <form action={action} className="login-form">
    <label>New password<input name="password" type="password" autoComplete="new-password" minLength={12} maxLength={128} required/></label>
    <label>Confirm password<input name="confirmation" type="password" autoComplete="new-password" minLength={12} maxLength={128} required/></label>
    <p className="auth-help">Use 12–128 characters. Your account’s analyst role is assigned by the project administrator.</p>
    {error && <p className="error" role="alert">{error}</p>}
    <button className="primary" disabled={pending}>{pending ? "Saving…" : "Save password & open dashboard"}</button>
  </form>;
}
