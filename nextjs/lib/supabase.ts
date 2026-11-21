import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";

export const cloudMode = process.env.DEFENDER_MODE === "supabase";

export function config() {
  const url = process.env.SUPABASE_URL?.trim();
  const key = process.env.SUPABASE_PUBLISHABLE_KEY?.trim();
  if (!url || !key?.startsWith("sb_publishable_")) return null;
  try {
    const endpoint = new URL(url);
    const localHttp = endpoint.protocol === "http:" && ["localhost", "127.0.0.1"].includes(endpoint.hostname);
    if (endpoint.protocol !== "https:" && !localHttp) return null;
    return { url: endpoint.origin, key };
  } catch {
    return null;
  }
}

export async function serverClient(settings: NonNullable<ReturnType<typeof config>>) {
  const jar = await cookies();
  return createServerClient(settings.url, settings.key, {
    cookies: {
      getAll: () => jar.getAll(),
      setAll(updates) {
        try {
          updates.forEach(({ name, value, options }) => jar.set(name, value, options));
        } catch {
          // Server components are read-only. Proxy refreshes cookies on navigation.
        }
      },
    },
  });
}
