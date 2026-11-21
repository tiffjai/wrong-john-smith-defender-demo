export type AnalystProfile = { booking_entity: string; review_role: string; data_scope?: string };

export function hasAllDataAccess(profile?: AnalystProfile): boolean {
  return profile?.review_role === "reviewer" && profile.data_scope === "all";
}

export function accessScopeLabel(profile: AnalystProfile): string {
  return hasAllDataAccess(profile) ? "All booking entities · UK & US" : `${profile.booking_entity} booking entity`;
}
