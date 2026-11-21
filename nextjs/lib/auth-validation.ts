export function passwordError(password: unknown, confirmation: unknown): string | null {
  if (typeof password !== "string" || password.length < 12 || password.length > 128) return "Use a password of 12–128 characters.";
  if (password !== confirmation) return "The passwords do not match.";
  return null;
}

export function authLinkDestination(type: string | null): string | null {
  if (type === "invite" || type === "recovery") return "/account/set-password";
  if (type === "signup" || type === "email") return "/";
  return null;
}
