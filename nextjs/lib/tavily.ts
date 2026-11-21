import { createHash } from "node:crypto";
import type { ResearchAction, ResearchPhoto, ResearchReport, ResearchSource } from "./research-types";

export const officialDomains = ["gov.uk", "ofac.treasury.gov", "sanctionssearch.ofac.treas.gov", "un.org", "consilium.europa.eu", "find-and-update.company-information.service.gov.uk"];

export class ResearchError extends Error {
  status: number;
  constructor(message: string, status: number) { super(message); this.status = status; }
}

export function publicUrl(value: unknown): string | null {
  if (typeof value !== "string" || value.length > 2000) return null;
  try {
    const url = new URL(value);
    // DNS names only. Requests go to Tavily, never directly to this URL.
    if (url.protocol !== "https:" || url.username || url.password || url.port ||
      !url.hostname.includes(".") || /[\[\]:]/.test(url.hostname) ||
      /^\d+(\.\d+){3}$/.test(url.hostname) || /\.(localhost|local|internal|test|invalid)$/.test(url.hostname)) return null;
    url.hash = "";
    return url.href;
  } catch { return null; }
}

export async function research(input: { case_id: string; action: ResearchAction; query: string; url?: string },
  apiKey: string, fetcher: typeof fetch = fetch): Promise<ResearchReport> {
  const extract = input.action === "extract";
  const query = input.action === "news" ? `${input.query} (sanctions OR fraud OR corruption OR investigation OR money laundering)` : input.query;
  const body = extract ? { urls: [input.url], extract_depth: "advanced", format: "text" } : {
    query, search_depth: "advanced", max_results: 5, include_answer: false,
    include_raw_content: false,
    ...(input.action === "official" || input.action === "photos" ? { topic: "general", include_domains: officialDomains } : { topic: "news", time_range: "month" }),
    ...(input.action === "photos" ? { include_images: true, include_image_descriptions: true } : {}),
  };
  let response: Response;
  try {
    response = await fetcher(`https://api.tavily.com/${extract ? "extract" : "search"}`, {
      method: "POST", headers: { Authorization: `Bearer ${apiKey}`, "Content-Type": "application/json" },
      body: JSON.stringify(body), cache: "no-store", signal: AbortSignal.timeout(45000),
    });
  } catch { throw new ResearchError("Research timed out or could not connect. Try again.", 504); }
  if (!response.ok) throw new ResearchError(response.status === 429 ? "Tavily rate or credit limit reached. Try later." : "Tavily research is unavailable. Check the server API key and credits.", response.status === 429 ? 429 : 502);
  const data = await response.json().catch(() => null);
  if (!data || !Array.isArray(data.results)) throw new ResearchError("Tavily returned an invalid response.", 502);
  const retrieved_at = new Date().toISOString();
  const sources: ResearchSource[] = [];
  const photos: ResearchPhoto[] = [];
  for (const item of data.results.slice(0, 5)) {
    if (!item || typeof item !== "object") continue;
    const url = publicUrl(item.url);
    if (!url) continue;
    if ((input.action === "official" || input.action === "photos") && !officialDomains.some(domain => new URL(url).hostname === domain || new URL(url).hostname.endsWith(`.${domain}`))) continue;
    // Only use images attributed to a specific returned source page. The global
    // image array may be unrelated to any listed identity and has no provenance.
    if (input.action === "photos" && Array.isArray(item.images)) {
      for (const image of item.images.slice(0, 5)) {
        const imageUrl = publicUrl(typeof image === "string" ? image : image?.url);
        if (!imageUrl || photos.length >= 6 || photos.some(photo => photo.url === imageUrl)) continue;
        photos.push({ evidence_id: `PHOTO-${createHash("sha256").update(`${input.case_id}|${retrieved_at}|${url}|${imageUrl}`).digest("hex").slice(0, 16)}`,
          url: imageUrl, source_url: url, source_title: typeof item.title === "string" ? item.title.slice(0, 500) : new URL(url).hostname,
          description: typeof image?.description === "string" ? image.description.slice(0, 500) : "Image from source page; subject unverified" });
      }
    }
    const content = extract ? item.raw_content : item.content;
    if (typeof content !== "string") continue;
    sources.push({ evidence_id: `WEB-${createHash("sha256").update(`${input.case_id}|${retrieved_at}|${url}|${content}`).digest("hex").slice(0, 16)}`,
      url, title: typeof item.title === "string" ? item.title.slice(0, 500) : new URL(url).hostname,
      content: content.slice(0, 20000), published_at: typeof item.published_date === "string" ? item.published_date : null });
  }
  return { case_id: input.case_id, action: input.action, query: extract ? input.url! : query, retrieved_at,
    request_id: typeof data.request_id === "string" ? data.request_id : null, sources, photos,
    failed_urls: Array.isArray(data.failed_results) ? data.failed_results.flatMap((item: { url?: unknown } | null) => publicUrl(item?.url) ?? []).slice(0, 5) : [],
    warning: "Unverified web evidence. Confirm the subject identity, source authority and effective dates. No results does not mean cleared. Retrieval time does not establish source freshness. Scores and decisions are unchanged." };
}
