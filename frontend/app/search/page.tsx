"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";

type Result = {
  openalex_id: string;
  title: string | null;
  abstract: string | null;
  authors: { name: string | null }[] | null;
  publication_date: string | null;
  doi: string | null;
  cited_by_count: number | null;
  score: number;
};

type Response = {
  retrieval_method: string;
  method_explanation: string;
  results: Result[];
};

export default function SearchPage() {
  const [query, setQuery] = useState("");
  const [method, setMethod] = useState<"lexical" | "semantic">("lexical");
  const [response, setResponse] = useState<Response | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!query.trim()) return;
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams({ q: query.trim(), method, limit: "10" });
      const result = await fetch(`/api/v1/search?${params.toString()}`, { cache: "no-store" });
      if (!result.ok) {
        const body = await result.json().catch(() => null);
        const detail = body?.detail;
        const message = typeof detail === "string"
          ? detail
          : Array.isArray(detail)
            ? detail.map(item => typeof item?.msg === "string" ? item.msg : "Invalid search request").join("; ")
            : `Search failed (${result.status})`;
        throw new Error(message);
      }
      setResponse(await result.json());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Search failed. Please try again.");
      setResponse(null);
    } finally {
      setLoading(false);
    }
  }

  return <main className="search-page">
    <header className="search-nav"><Link className="brand" href="/">Scholar<span>Signal</span></Link><Link className="text-link" href="/workspace">Research desk</Link></header>
    <section className="search-content">
      <p className="eyebrow"><span className="status-dot" /> OPENALEX PUBLICATIONS</p>
      <h1>Search the <em>literature.</em></h1>
      <p className="intro">Search ingested publication records with transparent lexical or semantic retrieval.</p>
      <form className="search-form" onSubmit={submit}>
        <label htmlFor="publication-query">Research question or keywords</label>
        <div className="search-controls">
          <input id="publication-query" value={query} onChange={event => setQuery(event.target.value)} placeholder="e.g. protein folding and language models" maxLength={500} required />
          <select aria-label="Retrieval method" value={method} onChange={event => setMethod(event.target.value as "lexical" | "semantic")}>
            <option value="lexical">Lexical</option><option value="semantic">Semantic</option>
          </select>
          <button className="button button-dark" type="submit" disabled={loading}>{loading ? "Searching…" : "Search"}</button>
        </div>
      </form>
      {error && <p className="form-error" role="alert">{error}</p>}
      {response && <section className="search-results" aria-live="polite">
        <div className="results-heading"><h2>Results</h2><span>{response.retrieval_method} · {response.results.length} results</span></div>
        <p className="method-note">{response.method_explanation}</p>
        {response.results.length === 0 && <p className="empty-results">No ingested publications matched this query.</p>}
        {response.results.map((item, index) => <article className="publication" key={item.openalex_id}>
          <div className="publication-meta"><span>0{index + 1}</span><span>{item.publication_date ?? "Date unavailable"}</span><span>Score {item.score.toFixed(3)}</span></div>
          <h3>{item.title ?? "Untitled publication"}</h3>
          {item.authors?.length ? <p className="publication-authors">{item.authors.map(author => author.name).filter(Boolean).join(", ")}</p> : null}
          {item.abstract && <p className="publication-abstract">{item.abstract}</p>}
          <div className="publication-footer"><span>{item.cited_by_count === null ? "Citations unavailable" : `${item.cited_by_count.toLocaleString()} citations`}</span>
            <a href={item.doi ? `https://doi.org/${encodeURIComponent(item.doi)}` : item.openalex_id} target="_blank" rel="noreferrer">View source ↗</a></div>
        </article>)}
      </section>}
    </section>
    <footer className="landing-footer"><span>ScholarSignal <span className="muted">· Search, grounded in source records.</span></span><span>Retrieval metrics require a labelled evaluation set.</span></footer>
  </main>;
}
