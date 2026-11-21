import test from "node:test";
import assert from "node:assert/strict";
import { passwordError, authLinkDestination } from "../lib/auth-validation.ts";

test("password setup validates length and matching confirmation", () => {
  for (const password of [null, "short", "a".repeat(129)]) assert.ok(passwordError(password, password));
  assert.match(passwordError("long-passphrase", "different"), /do not match/);
  assert.equal(passwordError("a".repeat(12), "a".repeat(12)), null);
  assert.equal(passwordError("a".repeat(128), "a".repeat(128)), null);
});

test("auth links have fixed local destinations and reject unsupported types", () => {
  assert.equal(authLinkDestination("invite"), "/account/set-password");
  assert.equal(authLinkDestination("recovery"), "/account/set-password");
  assert.equal(authLinkDestination("signup"), "/");
  for (const type of [null, "https://evil.example", "//evil.example", "magiclink", "other"]) assert.equal(authLinkDestination(type), null);
});
