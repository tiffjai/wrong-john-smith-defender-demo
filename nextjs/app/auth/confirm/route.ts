import { NextResponse } from "next/server";
import type { EmailOtpType } from "@supabase/supabase-js";
import { cloudMode, config, serverClient } from "../../../lib/supabase";
import { authLinkDestination } from "../../../lib/auth-validation";
import { requestOrigin } from "../../../lib/request-origin";

export async function GET(request: Request) {
  const url = new URL(request.url);
  const type = url.searchParams.get("type");
  const destination = authLinkDestination(type);
  const token_hash = url.searchParams.get("token_hash");
  const settings = cloudMode ? config() : null;
  if (settings && token_hash && destination) {
    const client = await serverClient(settings);
    const { error } = await client.auth.verifyOtp({ token_hash, type: type as EmailOtpType });
    if (!error) return NextResponse.redirect(new URL(destination, requestOrigin(request) ?? request.url));
  }
  return NextResponse.redirect(new URL("/login?error=link", requestOrigin(request) ?? request.url));
}
