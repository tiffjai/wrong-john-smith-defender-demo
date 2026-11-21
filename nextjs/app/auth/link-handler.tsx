"use client";

import { useEffect, useRef, useState } from "react";
import { createBrowserClient } from "@supabase/ssr";
import { authLinkDestination } from "../../lib/auth-validation";

// Supabase's default invitation template returns tokens in the URL fragment.
// Handle it on every page, including links issued before our callback existed.
export default function AuthLinkHandler({ settings }: { settings: { url: string; key: string } | null }) {
  const started = useRef(false);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!settings || started.current) return;
    const params = new URLSearchParams(window.location.hash.slice(1));
    if (!params.has("access_token") && !params.has("error_description")) return;
    started.current = true;
    setBusy(true);
    const access_token = params.get("access_token");
    const refresh_token = params.get("refresh_token");
    const destination = authLinkDestination(params.get("type"));
    // Remove bearer credentials from browser history before any further navigation.
    window.history.replaceState(null, "", window.location.pathname + window.location.search);
    if (!access_token || !refresh_token || !destination) {
      window.location.replace("/login?error=link"); return;
    }
    const client = createBrowserClient(settings.url, settings.key, { auth: { detectSessionInUrl: false } });
    void client.auth.setSession({ access_token, refresh_token }).then(({ error }) => {
      window.location.replace(error ? "/login?error=link" : destination);
    }).catch(() => window.location.replace("/login?error=link"));
  }, [settings]);
  return busy ? <div className="auth-link-progress" role="status">Verifying your secure email link…</div> : null;
}
