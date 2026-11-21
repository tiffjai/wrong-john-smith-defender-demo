export type ResearchAction = "official" | "news" | "extract" | "photos";
export type ResearchPhoto = {
  evidence_id: string; url: string; source_url: string; source_title: string; description: string;
};
export type ResearchSource = {
  evidence_id: string; title: string; url: string; content: string; published_at: string | null;
};
export type ResearchReport = {
  case_id: string; action: ResearchAction; query: string; retrieved_at: string;
  request_id: string | null; sources: ResearchSource[]; failed_urls: string[];
  warning: string; photos?: ResearchPhoto[];
};
