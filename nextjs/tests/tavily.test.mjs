import test from "node:test";
import assert from "node:assert/strict";
import { publicUrl, research } from "../lib/tavily.ts";

const source = { title: "Namesake investigation", url: "https://www.gov.uk/example", content: "Unverified namesake", raw_content: "Source text", published_date: "2026-11-20" };

test("official search restricts domains and retains attributable evidence without decisions", async () => {
  const report = await research({ case_id: "CASE-08", action: "official", query: "John Smith" }, "secret", async (url, options) => {
    assert.equal(url, "https://api.tavily.com/search");
    assert.equal(options.headers.Authorization, "Bearer secret");
    assert.equal(options.cache, "no-store");
    const body = JSON.parse(options.body);
    assert.ok(body.include_domains.includes("gov.uk"));
    assert.equal(body.include_answer, false);
    return Response.json({ request_id: "req-1", results: [source, { ...source, url: "https://gov.uk.evil.com/example" }, { ...source, url: "javascript:alert(1)" }] });
  });
  assert.equal(report.sources.length, 1);
  assert.match(report.sources[0].evidence_id, /^WEB-[a-f0-9]{16}$/);
  assert.equal(report.request_id, "req-1");
  assert.equal(report.sources[0].published_at, "2026-11-20");
  assert.equal(report.decision, undefined);
  assert.match(report.warning, /No results does not mean cleared/);
});

test("adverse media uses recent news and explicit risk terms", async () => {
  const report = await research({ case_id: "CASE-08", action: "news", query: "John Smith UK" }, "secret", async (_url, options) => {
    const body = JSON.parse(options.body);
    assert.equal(body.topic, "news");
    assert.equal(body.time_range, "month");
    assert.match(body.query, /John Smith UK.*fraud/);
    assert.equal(body.include_domains, undefined);
    return Response.json({ results: [] });
  });
  assert.deepEqual(report.sources, []);
  assert.match(report.query, /investigation/);
});

test("extraction preserves text and partial failures", async () => {
  const report = await research({ case_id: "CASE-08", action: "extract", query: "John Smith", url: source.url }, "secret", async (url, options) => {
    assert.equal(url, "https://api.tavily.com/extract");
    assert.deepEqual(JSON.parse(options.body).urls, [source.url]);
    return Response.json({ results: [source], failed_results: [{ url: "https://example.com/missing" }] });
  });
  assert.equal(report.sources[0].content, "Source text");
  assert.deepEqual(report.failed_urls, ["https://example.com/missing"]);
});

test("errors are actionable and never expose upstream secrets", async () => {
  const input = { case_id: "CASE-08", action: "official", query: "John Smith" };
  for (const status of [401, 429, 500]) {
    await assert.rejects(research(input, "secret", async () => new Response("secret", { status })), error => error.status === (status === 429 ? 429 : 502) && !error.message.includes("secret"));
  }
  await assert.rejects(research(input, "secret", async () => { throw new Error("secret"); }), error => error.status === 504);
  await assert.rejects(research(input, "secret", async () => Response.json({})), error => error.status === 502);
});

test("source links reject nonpublic and unsafe URL forms", () => {
  for (const url of ["http://example.com", "https://127.0.0.1", "https://[::1]", "https://localhost", "https://foo.internal", "https://user:pass@example.com", "javascript:alert(1)", "https://example.com:8443"]) assert.equal(publicUrl(url), null, url);
  assert.equal(publicUrl("https://www.gov.uk/check#section"), "https://www.gov.uk/check");
});

test("photo search retains source attribution and rejects unsafe, duplicate and unattributed images", async () => {
  const report = await research({ case_id: "CASE-08", action: "photos", query: "Listed person" }, "secret", async (_url, options) => {
    const body = JSON.parse(options.body);
    assert.equal(body.include_images, true);
    assert.equal(body.include_image_descriptions, true);
    assert.equal(body.topic, "general");
    assert.ok(body.include_domains.includes("gov.uk"));
    return Response.json({ images: [{ url: "https://images.example.com/unattributed.jpg" }], results: [
      { ...source, images: [{ url: "https://images.example.com/portrait.jpg", description: "Unverified portrait" }, { url: "http://127.0.0.1/private" }, { url: "javascript:alert(1)" }, { url: "https://images.example.com/portrait.jpg" }] },
      { ...source, url: "https://gov.uk.evil.com/person", images: [{ url: "https://images.example.com/wrong.jpg" }] },
    ] });
  });
  assert.equal(report.photos.length, 1);
  assert.equal(report.photos[0].source_url, source.url);
  assert.equal(report.photos[0].description, "Unverified portrait");
  assert.match(report.photos[0].evidence_id, /^PHOTO-[a-f0-9]{16}$/);
  assert.equal(report.photos[0].verified, undefined);
});

test("photo search with no attributed images has an honest empty result", async () => {
  const report = await research({ case_id: "CASE-08", action: "photos", query: "Fictional person" }, "secret", async () => Response.json({ results: [] }));
  assert.deepEqual(report.photos, []);
});
