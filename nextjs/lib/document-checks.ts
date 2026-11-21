import type { IdentityDocument } from "./types";

export function compareDocuments(documents: IdentityDocument[]) {
  const overlaps: [IdentityDocument, IdentityDocument][] = [];
  const conflicts: [IdentityDocument, IdentityDocument][] = [];
  for (const [index, left] of documents.entries()) {
    for (const right of documents.slice(index + 1)) {
      if (left.customer_id !== right.customer_id) {
        if (left.document_key === right.document_key && left.verified_dob !== right.verified_dob) {
          conflicts.push([left, right]);
        }
        continue;
      }
      const overlap = left.issued <= right.expires && right.issued <= left.expires
        && (!left.superseded_on || right.issued < left.superseded_on)
        && (!right.superseded_on || left.issued < right.superseded_on);
      if (overlap && left.verified_dob === right.verified_dob) {
        overlaps.push([left, right]);
      }
    }
  }
  return { overlaps, conflicts };
}
