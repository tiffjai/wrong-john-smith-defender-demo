import test from "node:test";
import assert from "node:assert/strict";
import { isSameOrigin, requestOrigin } from "../lib/request-origin.ts";

const request = (headers) => new Request("http://localhost:3000/api/research", { method: "POST", headers });

test("uses browser-facing Host when Next rewrites its internal URL", () => {
  const req = request({ host: "127.0.0.1:3000", origin: "http://127.0.0.1:3000" });
  assert.equal(isSameOrigin(req), true);
  assert.equal(requestOrigin(req), "http://127.0.0.1:3000");
  assert.equal(isSameOrigin(request({ host: "localhost:3000", origin: "http://localhost:3000" })), true);
});

test("rejects cross-origin, missing, null, scheme and port mismatches", () => {
  for (const origin of [undefined, "null", "https://evil.example", "http://127.0.0.1:3001", "https://127.0.0.1:3000", "http://localhost:3000"]) {
    const headers = { host: "127.0.0.1:3000" };
    if (origin !== undefined) headers.origin = origin;
    assert.equal(isSameOrigin(request(headers)), false, String(origin));
  }
});

test("does not allow forwarded-host spoofing or malformed host values", () => {
  assert.equal(isSameOrigin(request({ host: "localhost:3000", origin: "https://evil.example", "x-forwarded-host": "evil.example" })), false);
  assert.equal(requestOrigin(request({ host: "localhost:3000@evil.example" })), null);
  assert.equal(requestOrigin(request({ host: "public.example" })), "http://public.example");
});
