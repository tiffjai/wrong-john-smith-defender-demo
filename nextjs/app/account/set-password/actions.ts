"use server";

import { redirect } from "next/navigation";
import { cloudMode, config, serverClient } from "../../../lib/supabase";
import { passwordError } from "../../../lib/auth-validation";

export async function setPassword(_: string, form: FormData) {
  const password = form.get("password");
  const invalid = passwordError(password, form.get("confirmation"));
  if (invalid) return invalid;
  const settings = cloudMode ? config() : null;
  if (!settings) return "Supabase authentication is unavailable.";
  const client = await serverClient(settings);
  const { data, error: sessionError } = await client.auth.getUser();
  if (sessionError || !data.user) return "Your link expired. Request a new password setup link.";
  const { error } = await client.auth.updateUser({ password: password as string });
  if (error) return "Could not save this password. Try a stronger password, or request a new link.";
  redirect("/");
}
