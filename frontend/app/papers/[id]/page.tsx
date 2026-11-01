"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { doiUrl, openAlexUrl } from "../../links";

type Paper = {
  id: number; openalex_id: string; title: string | null; abstract: string | null;
  authors: { name?: string | null }[] | null; publication_date: string | null;
  doi: string | null; concepts: { display_name?: string }[] | null;
  topics: { display_name?: string }[] | null; cited_by_count: number | null;
  source: string; retrieved_at: string; venue: string | null; references: string[];
};
type Related = { id: number; openalex_id: string; title: string | null; score: number; explanation: string | null };

export default function PaperPage() {
  const params = useParams<{ id: string }>();
  const [paper, setPaper] = useState<Paper | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [related, setRelated] = useState<Related[]>([]);
  useEffect(() => {
    fetch(`/api/v1/publications/${encodeURIComponent(params.id)}`, { cache: "no-store" })
      .then(async response => {
        if (!response.ok) throw new Error(response.status === 404 ? "This publication was not found in the library." : "Could not load publication details.");
        const record = await response.json();
        setPaper(record);
        const relatedResponse = await fetch(`/api/v1/publications/${encodeURIComponent(params.id)}/related`, { cache: "no-store" });
        if (relatedResponse.ok) setRelated((await relatedResponse.json()).results);
      }).catch(reason => setError(reason instanceof Error ? reason.message : "Could not load publication details."));
  }, [params.id]);
  async function save() {
    const response = await fetch("/api/v1/workspace/saved", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ publication_id: Number(params.id) }) });
    setMessage(response.status === 204 ? "Saved to your research desk." : response.status === 401 ? "Sign in to save this paper." : "Could not save this paper.");
  }
  return <main className="search-page"><header className="search-nav"><Link className="brand" href="/">Scholar<span>Signal</span></Link><nav className="detail-nav"><Link className="text-link" href="/search">Back to search</Link><Link className="text-link" href="/workspace">Research desk</Link></nav></header>
    <article className="detail-content">{error ? <p className="form-error" role="alert">{error}</p> : !paper ? <p className="loading-state" role="status">Loading publication…</p> : <>
      <p className="eyebrow"><span className="status-dot" /> PUBLICATION RECORD · {paper.source}</p><h1>{paper.title ?? "Untitled publication"}</h1>
      <div className="detail-meta">{paper.publication_date?.slice(0, 10) ?? "Date unavailable"}{paper.venue ? ` · ${paper.venue}` : ""}{paper.cited_by_count === null ? " · Citation count unavailable" : ` · ${paper.cited_by_count.toLocaleString()} citations`}</div>
      {paper.authors?.length ? <p className="detail-authors">{paper.authors.map(a => a.name).filter(Boolean).join(", ")}</p> : null}
      <div className="detail-actions"><button className="button button-dark" onClick={save}>Save paper</button>{paper.doi && <a className="button button-light" href={doiUrl(paper.doi)} target="_blank" rel="noreferrer">Open DOI source ↗</a>}<a className="text-link" href={openAlexUrl(paper.openalex_id)} target="_blank" rel="noreferrer">OpenAlex ↗</a></div>
      {message && <p role="status" className="form-status">{message}</p>}
      <section className="detail-section"><h2>Abstract</h2><p>{paper.abstract ?? "Abstract unavailable in the source record."}</p></section>
      {!!(paper.topics?.length || paper.concepts?.length) && <section className="detail-section"><h2>Topics and concepts</h2><div className="topic-list">{[...(paper.topics ?? []), ...(paper.concepts ?? [])].map((item, index) => item.display_name ? <span key={`${item.display_name}-${index}`}>{item.display_name}</span> : null)}</div></section>}
      <section className="detail-section"><h2>Source record</h2><dl><dt>OpenAlex ID</dt><dd>{paper.openalex_id}</dd><dt>DOI</dt><dd>{paper.doi ?? "Unavailable"}</dd><dt>Retrieved</dt><dd>{new Date(paper.retrieved_at).toLocaleString()}</dd></dl></section>
      {paper.references.length > 0 && <section className="detail-section"><h2>References in the source record</h2><p className="reference-note">These are OpenAlex reference identifiers supplied with this record.</p><ul className="reference-list">{paper.references.map(id => <li key={id}><a href={id} target="_blank" rel="noreferrer">{id.replace("https://openalex.org/", "")} ↗</a></li>)}</ul></section>}
      {related.length > 0 && <section className="detail-section"><h2>Related in your library</h2><p className="reference-note">Ranked by cosine similarity between locally stored FastEmbed vectors.</p><ul className="related-list">{related.map(item => <li key={item.id}><Link href={`/papers/${item.id}`}>{item.title ?? item.openalex_id}</Link><span>{item.score.toFixed(3)}</span></li>)}</ul></section>}
    </>}</article><footer className="landing-footer"><span>ScholarSignal · Source fields are shown when available.</span></footer></main>;
}
