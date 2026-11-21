"use server";

import { redirect } from "next/navigation";
import { cloudMode, config, serverClient } from "../../lib/supabase";

export async function signIn(_: string, form: FormData) {
  const settings = cloudMode ? config() : null;
  if (!settings) return "Supabase connection is not configured.";
  const email = form.get("email");
  const password = form.get("password");
  if (typeof email !== "string" || typeof password !== "string" || !email.trim() || !password) {
    return "Enter your email and password.";
  }
  const supabase = await serverClient(settings);
  const { error } = await supabase.auth.signInWithPassword({ email: email.trim(), password });
  if (error) return "Sign-in failed. Check the account details and Supabase connection.";
  redirect("/");
}

export async function signOut() {
  const settings = cloudMode ? config() : null;
  if (settings) {
    const supabase = await serverClient(settings);
    await supabase.auth.signOut({ scope: "local" });
  }
  redirect("/login");
}
