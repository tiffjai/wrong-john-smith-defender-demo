import case01 from "../data/evidence_packet_CASE-01.json";
import case03 from "../data/evidence_packet_CASE-03.json";
import case08 from "../data/evidence_packet_CASE-08.json";
import case11 from "../data/evidence_packet_CASE-11.json";
import case12 from "../data/evidence_packet_CASE-12.json";
import caseIndex from "../data/case-index.json";
import ownershipReplay from "../data/recommendation_CASE-11.json";
import type { Case, Packet } from "./types";

const packets: Record<string, Packet> = {
  "CASE-01": case01, "CASE-03": case03, "CASE-08": case08, "CASE-11": case11, "CASE-12": case12,
};
export const fixtures: Case[] = caseIndex.map((entry) => ({
  ...entry, packet: packets[entry.id], recommendation: entry.id === "CASE-11" ? ownershipReplay : null,
}));

import noteFixtures from "../data/case-notes.json";
import type { CaseNote } from "./types";
export const demoNotes: CaseNote[] = noteFixtures;
