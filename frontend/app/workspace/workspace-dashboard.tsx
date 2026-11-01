"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";

type Paper = { id: number; openalex_id: string; title: string | null; publication_date: string | null; doi: string | null; cited_by_count: number | null };
type Collection = { id: number; name: string; description: string | null; publication_count: number };
type CollectionPaper = { id: number; title: string | null; openalex_id: string };
type Note = { id: number; title: string; body: string; publication_id: number | null; updated_at: string };
type HistoryItem = { id: number; query: string; method: string; result_count: number; created_at: string };

async function get<T>(path: string): Promise<T> {
  const response = await fetch(`/api/v1${path}`, { cache: "no-store" });
  if (!response.ok) throw new Error(`Request failed (${response.status})`);
  return response.json();
}

export function WorkspaceDashboard() {
  const [saved, setSaved] = useState<Paper[]>([]);
  const [collections, setCollections] = useState<Collection[]>([]);
  const [notes, setNotes] = useState<Note[]>([]);
  const [recent, setRecent] = useState<Paper[]>([]);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [openCollection, setOpenCollection] = useState<number | null>(null);
  const [collectionPapers, setCollectionPapers] = useState<CollectionPaper[]>([]);
  const [error, setError] = useState("");
  const [collectionName, setCollectionName] = useState("");
  const [collectionDescription, setCollectionDescription] = useState("");
  const [noteTitle, setNoteTitle] = useState("");
  const [noteBody, setNoteBody] = useState("");
  const [notePaper, setNotePaper] = useState("");

  async function refresh() {
    setError("");
    try {
      const [savedItems, collectionItems, noteItems, recentItems, historyItems] = await Promise.all([
        get<Paper[]>("/workspace/saved"), get<Collection[]>("/workspace/collections"),
        get<Note[]>("/workspace/notes"), get<Paper[]>("/workspace/recent"), get<HistoryItem[]>("/search/history"),
      ]);
      setSaved(savedItems); setCollections(collectionItems); setNotes(noteItems); setRecent(recentItems); setHistory(historyItems);
    } catch { setError("Could not load your research desk. Refresh to try again."); }
  }
  useEffect(() => { void refresh(); }, []);

  async function submitCollection(event: FormEvent) {
    event.preventDefault(); setError("");
    const response = await fetch("/api/v1/workspace/collections", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: collectionName, description: collectionDescription || null }) });
    if (!response.ok) { setError(response.status === 409 ? "You already have a collection with that name." : "Could not create collection."); return; }
    setCollectionName(""); setCollectionDescription(""); await refresh();
  }
  async function submitNote(event: FormEvent) {
    event.preventDefault(); setError("");
    const response = await fetch("/api/v1/workspace/notes", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ title: noteTitle, body: noteBody, publication_id: notePaper ? Number(notePaper) : null }) });
    if (!response.ok) { setError("Could not save note."); return; }
    setNoteTitle(""); setNoteBody(""); setNotePaper(""); await refresh();
  }
  async function unsave(id: number) {
    await fetch(`/api/v1/workspace/saved/${id}`, { method: "DELETE" }); await refresh();
  }
  async function deleteCollection(id: number) {
    await fetch(`/api/v1/workspace/collections/${id}`, { method: "DELETE" }); await refresh();
  }
  async function deleteNote(id: number) {
    await fetch(`/api/v1/workspace/notes/${id}`, { method: "DELETE" }); await refresh();
  }
  async function addToCollection(collectionId: number, publicationId: number) {
    const response = await fetch(`/api/v1/workspace/collections/${collectionId}/publications`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ publication_id: publicationId }) });
    if (!response.ok) setError("Could not add paper to collection."); else { setOpenCollection(collectionId); await loadCollection(collectionId); await refresh(); }
  }
  async function loadCollection(collectionId: number) {
    try { setCollectionPapers(await get<CollectionPaper[]>(`/workspace/collections/${collectionId}/publications`)); }
    catch { setError("Could not load papers in this collection."); }
  }
  async function toggleCollection(collectionId: number) {
    if (openCollection === collectionId) { setOpenCollection(null); return; }
    setOpenCollection(collectionId); await loadCollection(collectionId);
  }
  async function removeFromCollection(collectionId: number, publicationId: number) {
    const response = await fetch(`/api/v1/workspace/collections/${collectionId}/publications/${publicationId}`, { method: "DELETE" });
    if (!response.ok) setError("Could not remove paper from collection."); else { await loadCollection(collectionId); await refresh(); }
  }

  return <div className="desk-grid">
    {error && <p className="form-error desk-error" role="alert">{error}</p>}
    <section className="desk-panel desk-wide"><div className="desk-heading"><div><p className="eyebrow">YOUR LIBRARY</p><h2>Saved papers <span>{saved.length}</span></h2></div><Link className="text-link" href="/search">Discover more ↗</Link></div>
      {saved.length ? <div className="desk-list">{saved.map(paper => <article className="desk-item" key={paper.id}><div><Link href={`/papers/${paper.id}`} className="desk-item-title">{paper.title ?? "Untitled publication"}</Link><p>{paper.publication_date?.slice(0, 4) ?? "Year unavailable"} · {paper.openalex_id}</p></div><div className="desk-item-actions">{collections.length > 0 && <select aria-label={`Add ${paper.title ?? "paper"} to collection`} defaultValue="" onChange={event => { if (event.target.value) void addToCollection(Number(event.target.value), paper.id); event.target.value = ""; }}><option value="">Add to collection…</option>{collections.map(collection => <option key={collection.id} value={collection.id}>{collection.name}</option>)}</select>}<button className="text-button" onClick={() => void unsave(paper.id)}>Remove</button></div></article>)}</div> : <p className="desk-empty">Papers you save from search will appear here.</p>}
    </section>
    <section className="desk-panel"><div className="desk-heading"><div><p className="eyebrow">ORGANISE</p><h2>Collections</h2></div></div><form className="desk-form" onSubmit={submitCollection}><label>Name<input value={collectionName} onChange={event => setCollectionName(event.target.value)} maxLength={120} required /></label><label>Description<input value={collectionDescription} onChange={event => setCollectionDescription(event.target.value)} maxLength={2000} /></label><button className="button button-dark" type="submit">Create collection</button></form>
      {collections.length ? <ul className="desk-compact-list">{collections.map(collection => <li key={collection.id}><div><strong>{collection.name}</strong><small>{collection.publication_count} {collection.publication_count === 1 ? "paper" : "papers"}{collection.description ? ` · ${collection.description}` : ""}</small>{openCollection === collection.id && <ul className="collection-paper-list">{collectionPapers.length ? collectionPapers.map(paper => <li key={paper.id}><Link href={`/papers/${paper.id}`}>{paper.title ?? paper.openalex_id}</Link><button className="text-button" onClick={() => void removeFromCollection(collection.id, paper.id)}>Remove</button></li>) : <li className="desk-empty">No papers in this collection yet.</li>}</ul>}</div><div className="desk-item-actions"><button className="text-button" onClick={() => void toggleCollection(collection.id)}>{openCollection === collection.id ? "Hide papers" : "View papers"}</button><button className="text-button" onClick={() => void deleteCollection(collection.id)}>Delete</button></div></li>)}</ul> : <p className="desk-empty">Create a collection to organise saved research.</p>}
    </section>
    <section className="desk-panel"><div className="desk-heading"><div><p className="eyebrow">THINKING SPACE</p><h2>Research notes</h2></div></div><form className="desk-form" onSubmit={submitNote}><label>Title<input value={noteTitle} onChange={event => setNoteTitle(event.target.value)} maxLength={160} required /></label><label>Paper (optional)<select value={notePaper} onChange={event => setNotePaper(event.target.value)}><option value="">No linked paper</option>{saved.map(paper => <option key={paper.id} value={paper.id}>{paper.title ?? paper.openalex_id}</option>)}</select></label><label>Note<textarea value={noteBody} onChange={event => setNoteBody(event.target.value)} maxLength={20000} rows={3} required /></label><button className="button button-dark" type="submit">Save note</button></form>
      {notes.length ? <div className="desk-compact-list">{notes.map(note => <article className="desk-note" key={note.id}><div><strong>{note.title}</strong><p>{note.body}</p>{note.publication_id && <Link href={`/papers/${note.publication_id}`}>Open linked paper ↗</Link>}</div><button className="text-button" onClick={() => void deleteNote(note.id)}>Delete</button></article>)}</div> : <p className="desk-empty">Your notes will stay private to your account.</p>}
    </section>
    <section className="desk-panel"><div className="desk-heading"><div><p className="eyebrow">PICK UP WHERE YOU LEFT OFF</p><h2>Recently viewed</h2></div></div>{recent.length ? <ul className="desk-compact-list">{recent.map(paper => <li key={paper.id}><Link href={`/papers/${paper.id}`}>{paper.title ?? "Untitled publication"}</Link></li>)}</ul> : <p className="desk-empty">Viewed paper details will be listed here.</p>}</section>
    <section className="desk-panel"><div className="desk-heading"><div><p className="eyebrow">YOUR ACTIVITY</p><h2>Search history</h2></div></div>{history.length ? <ul className="desk-compact-list">{history.map(item => <li key={item.id}><div><Link href={`/search?q=${encodeURIComponent(item.query)}&method=${encodeURIComponent(item.method)}`}>{item.query}</Link><small>{item.method} · {item.result_count} matches · {new Date(item.created_at).toLocaleDateString()}</small></div></li>)}</ul> : <p className="desk-empty">Sign-in searches will appear here.</p>}</section>
  </div>;
}
