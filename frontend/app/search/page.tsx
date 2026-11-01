"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { doiUrl, openAlexUrl } from "../links";

type Result = {
  id: number;
  openalex_id: string;
  title: string | null;
  abstract: string | null;
  authors: { name?: string | null }[] | null;
  publication_date: string | null;
  doi: string | null;
  cited_by_count: number | null;
  score: number;
  explanation: string | null;
};
type SearchResponse = {
  retrieval_method: string;
  method_explanation: string;
  results: Result[];
  total: number;
  results_capped: boolean;
  page: number;
  per_page: number;
};
type Method = "lexical" | "semantic" | "hybrid";

export default function SearchPage() {
  const [query, setQuery] = useState("");
  const [method, setMethod] = useState<Method>("hybrid");
  const [yearFrom, setYearFrom] = useState("");
  const [yearTo, setYearTo] = useState("");
  const [author, setAuthor] = useState("");
  const [topic, setTopic] = useState("");
  const [sortBy, setSortBy] = useState("relevance");
  const [page, setPage] = useState(1);
  const [response, setResponse] = useState<SearchResponse | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const savedQuery = params.get("q");
    if (savedQuery) setQuery(savedQuery.slice(0, 500));
    const savedMethod = params.get("method");
    if (savedMethod === "lexical" || savedMethod === "semantic" || savedMethod === "hybrid") setMethod(savedMethod);
  }, []);

  async function runSearch(event?: FormEvent<HTMLFormElement>, nextPage = 1) {
    event?.preventDefault();
    if (!query.trim()) return;
    setLoading(true);
    setError("");
    setNotice("");
    const params = new URLSearchParams({ q: query.trim(), method, page: String(nextPage), per_page: "10", sort_by: sortBy });
    if (yearFrom) params.set("year_from", yearFrom);
    if (yearTo) params.set("year_to", yearTo);
    if (author.trim()) params.set("author", author.trim());
    if (topic.trim()) params.set("topic", topic.trim());
    try {
      const result = await fetch(`/api/v1/search?${params}`, { cache: "no-store" });
      const body = await result.json().catch(() => null);
      if (!result.ok) {
        const detail = body?.detail;
        const message = typeof detail === "string" ? detail : Array.isArray(detail) ? detail.map((item: {msg?: string}) => item.msg ?? "Invalid search request").join("; ") : `Search failed (${result.status})`;
        throw new Error(message);
      }
      setResponse(body);
      setPage(nextPage);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Search failed. Please try again.");
      setResponse(null);
    } finally { setLoading(false); }
  }

  async function save(publicationId: number) {
    setNotice("");
    const result = await fetch("/api/v1/workspace/saved", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ publication_id: publicationId }) });
    setNotice(result.status === 204 ? "Saved to your research desk." : result.status === 401 ? "Sign in to save papers." : "Could not save this paper.");
  }

  return <main className="search-page">
    <header className="search-nav"><Link className="brand" href="/">Scholar<span>Signal</span></Link><Link className="text-link" href="/workspace">Research desk</Link></header>
    <section className="search-content">
      <p className="eyebrow"><span className="status-dot" /> OPENALEX PUBLICATIONS</p>
      <h1>Search the <em>literature.</em></h1>
      <p className="intro">Explore the records available in your library. Choose transparent lexical, local semantic, or hybrid retrieval.</p>
      <form className="search-form" onSubmit={event => runSearch(event)}>
        <label htmlFor="publication-query">Research question or keywords</label>
        <div className="search-controls">
          <input id="publication-query" value={query} onChange={event => setQuery(event.target.value)} placeholder="e.g. protein folding and language models" maxLength={500} required />
          <select aria-label="Retrieval method" value={method} onChange={event => setMethod(event.target.value as Method)}><option value="hybrid">Hybrid</option><option value="lexical">Lexical</option><option value="semantic">Semantic</option></select>
          <button className="button button-dark" type="submit" disabled={loading}>{loading ? "Searching…" : "Search"}</button>
        </div>
        <details className="search-filters"><summary>Filters and sorting</summary><div className="filter-grid">
          <label>From year<input inputMode="numeric" type="number" min="1800" max="2100" value={yearFrom} onChange={event => setYearFrom(event.target.value)} /></label>
          <label>To year<input inputMode="numeric" type="number" min="1800" max="2100" value={yearTo} onChange={event => setYearTo(event.target.value)} /></label>
          <label>Author contains<input value={author} onChange={event => setAuthor(event.target.value)} maxLength={200} /></label>
          <label>Topic contains<input value={topic} onChange={event => setTopic(event.target.value)} maxLength={200} /></label>
          <label>Sort by<select value={sortBy} onChange={event => setSortBy(event.target.value)}><option value="relevance">Relevance</option><option value="date">Publication date</option><option value="citations">Citations</option></select></label>
        </div></details>
      </form>
      {error && <p className="form-error" role="alert">{error}</p>}
      {notice && <p className="form-status" role="status">{notice}</p>}
      {loading && <p className="loading-state" role="status">Searching your publication library…</p>}
      {response && !loading && <section className="search-results" aria-live="polite">
        <div className="results-heading"><h2>Results</h2><span>{response.results_capped ? `Up to ${response.total}+ candidates · capped` : `${response.total} records`} · page {page}</span></div>
        <p className="method-note">{response.method_explanation}</p>
        {response.results.length === 0 && <p className="empty-results">No ingested publications matched this query and its filters.</p>}
        {response.results.map((item, index) => <article className="publication" key={item.openalex_id}>
          <div className="publication-meta"><span>{String((page - 1) * 10 + index + 1).padStart(2, "0")}</span><span>{item.publication_date?.slice(0, 4) ?? "Year unavailable"}</span><span>{item.explanation ?? `${method} score ${item.score.toFixed(3)}`}</span></div>
          <h3><Link href={`/papers/${item.id}`}>{item.title ?? "Untitled publication"}</Link></h3>
          {item.authors?.length ? <p className="publication-authors">{item.authors.map(person => person.name).filter(Boolean).join(", ")}</p> : null}
          {item.abstract && <p className="publication-abstract">{item.abstract}</p>}
          <div className="publication-footer"><span>{item.cited_by_count === null ? "Citations unavailable" : `${item.cited_by_count.toLocaleString()} citations`}</span><button type="button" className="text-button" onClick={() => save(item.id)}>Save paper</button>{item.doi && <a href={doiUrl(item.doi)} target="_blank" rel="noreferrer">DOI source ↗</a>}<a href={openAlexUrl(item.openalex_id)} target="_blank" rel="noreferrer">OpenAlex source ↗</a></div>
        </article>)}
        <nav className="pagination" aria-label="Search result pages"><button className="button button-light" disabled={loading || page <= 1} onClick={() => runSearch(undefined, page - 1)}>Previous</button><span>Page {page}</span><button className="button button-light" disabled={loading || page * response.per_page >= response.total} onClick={() => runSearch(undefined, page + 1)}>Next</button></nav>
      </section>}
    </section>
    <footer className="landing-footer"><span>ScholarSignal <span className="muted">· Search, grounded in source records.</span></span><span>Evaluation is limited to the documented pilot labels.</span></footer>
  </main>;
}
