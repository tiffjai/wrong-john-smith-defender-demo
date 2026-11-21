// Next's internal request URL can use localhost even when the browser uses
// 127.0.0.1. Match the browser-facing Host, retaining the protocol and port.
// Do not trust arbitrary X-Forwarded-Host values from clients.
export function requestOrigin(request: Request): string | null {
  try {
    const internal = new URL(request.url);
    const host = request.headers.get("host") ?? internal.host;
    if (!host || /[\s/@?#\\]/.test(host)) return null;
    return new URL(`${internal.protocol}//${host}`).origin;
  } catch { return null; }
}

export function isSameOrigin(request: Request): boolean {
  const origin = request.headers.get("origin");
  return !!origin && origin !== "null" && origin === requestOrigin(request);
}
