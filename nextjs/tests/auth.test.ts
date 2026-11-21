// @vitest-environment node
import { beforeEach, expect, test, vi } from "vitest";

const auth = vi.hoisted(() => ({ getUser: vi.fn(), updateUser: vi.fn(), signInWithPassword: vi.fn(), signOut: vi.fn(), verifyOtp: vi.fn(), exchangeCodeForSession: vi.fn() }));
vi.mock("../lib/supabase", () => ({ cloudMode: true, config: () => ({ url: "https://project.supabase.co", key: "sb_publishable_test" }), serverClient: async () => ({ auth }) }));
vi.mock("next/navigation", () => ({ redirect: (path: string) => { throw new Error(`REDIRECT:${path}`); } }));
import { setPassword } from "../app/account/set-password/actions";
import { signIn, signOut } from "../app/login/actions";
import { GET as confirm } from "../app/auth/confirm/route";
import { GET as callback } from "../app/auth/callback/route";

beforeEach(() => vi.resetAllMocks());
const form = (entries: Record<string, string>) => {
  const data = new FormData();
  for (const [key, value] of Object.entries(entries)) data.set(key, value);
  return data;
};

test("password setup requires a verified session", async () => {
  auth.getUser.mockResolvedValue({ data: { user: null }, error: new Error("expired") });
  expect(await setPassword("", form({password: "a-long-passphrase", confirmation: "a-long-passphrase"}))).toMatch(/expired/);
  expect(auth.updateUser).not.toHaveBeenCalled();
});

test("password setup validates confirmation before contacting Supabase", async () => {
  expect(await setPassword("", form({password: "a-long-passphrase", confirmation: "different"}))).toMatch(/do not match/);
  expect(auth.getUser).not.toHaveBeenCalled();
});

test("password setup updates only the password and opens the dashboard", async () => {
  auth.getUser.mockResolvedValue({data: {user: {id: "assigned-user"}}, error: null});
  auth.updateUser.mockResolvedValue({error: null});
  await expect(setPassword("", form({password: "a-long-passphrase", confirmation: "a-long-passphrase", review_role: "reviewer"}))).rejects.toThrow("REDIRECT:/");
  expect(auth.updateUser).toHaveBeenCalledWith({password: "a-long-passphrase"});
});

test("login does not expose upstream error details", async () => {
  auth.signInWithPassword.mockResolvedValue({error: new Error("sensitive upstream detail")});
  const error = await signIn("", form({email: "demo@example.com", password: "wrong"}));
  expect(error).toMatch(/Sign-in failed/);
  expect(error).not.toContain("sensitive");
});

test("successful login and logout redirect without accepting role input", async () => {
  auth.signInWithPassword.mockResolvedValue({error: null});
  await expect(signIn("", form({email: "demo@example.com", password: "a-long-passphrase", role: "senior"}))).rejects.toThrow("REDIRECT:/");
  expect(auth.signInWithPassword).toHaveBeenCalledWith({email: "demo@example.com", password: "a-long-passphrase"});
  auth.signOut.mockResolvedValue({error: null});
  await expect(signOut()).rejects.toThrow("REDIRECT:/login");
  expect(auth.signOut).toHaveBeenCalledWith({scope: "local"});
});

test("invitation confirmation verifies token and ignores arbitrary next URLs", async () => {
  auth.verifyOtp.mockResolvedValue({error: null});
  const result = await confirm(new Request("http://localhost:3000/auth/confirm?token_hash=test-token&type=invite&next=https://evil.example", {headers: {host: "127.0.0.1:3000"}}));
  expect(result.headers.get("location")).toBe("http://127.0.0.1:3000/account/set-password");
  expect(auth.verifyOtp).toHaveBeenCalledWith({token_hash: "test-token", type: "invite"});
});

test("invalid links fail closed; PKCE exchange errors return to login", async () => {
  const invalid = await confirm(new Request("http://localhost:3000/auth/confirm?token_hash=x&type=unknown"));
  expect(invalid.headers.get("location")).toContain("/login?error=link");
  expect(auth.verifyOtp).not.toHaveBeenCalled();
  auth.exchangeCodeForSession.mockResolvedValue({error: new Error("invalid")});
  const failed = await callback(new Request("http://localhost:3000/auth/callback?code=invalid"));
  expect(failed.headers.get("location")).toContain("/login?error=link");
});
