import { NextResponse } from "next/server";
import { cloudMode, config, serverClient } from "../../../lib/supabase";
import { requestOrigin } from "../../../lib/request-origin";

export async function GET(request: Request) {
  const code = new URL(request.url).searchParams.get("code");
  const settings = cloudMode ? config() : null;
  if (settings && code) {
    const client = await serverClient(settings);
    const { error } = await client.auth.exchangeCodeForSession(code);
    if (!error) return NextResponse.redirect(new URL("/account/set-password", requestOrigin(request) ?? request.url));
  }
  return NextResponse.redirect(new URL("/login?error=link", requestOrigin(request) ?? request.url));
}
