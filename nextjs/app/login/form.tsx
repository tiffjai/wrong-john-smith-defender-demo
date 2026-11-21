"use client";

import { useActionState } from "react";
import { signIn } from "./actions";

export default function SignInForm() {
  const [error, submit, pending] = useActionState(signIn, "");
  return <form action={submit} className="login-form">
    <label>Email <input name="email" type="email" autoComplete="username" maxLength={254} required /></label>
    <label>Password <input name="password" type="password" autoComplete="current-password" required /></label>
    {error && <p className="error" role="alert">{error}</p>}
    <button className="primary" disabled={pending}>{pending ? "Signing in…" : "Sign in"}</button>
  </form>;
}
