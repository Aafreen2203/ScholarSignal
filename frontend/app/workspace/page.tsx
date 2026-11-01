import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import Link from "next/link";
import { LogoutButton } from "../logout-button";

type User = { id: number; email: string; display_name: string };

async function getUser(): Promise<User | null> {
  const token = (await cookies()).get("access_token")?.value;
  if (!token) return null;
  try {
    const response = await fetch(`${process.env.API_INTERNAL_URL ?? "http://localhost:8000"}/api/v1/auth/me`, { headers: { Cookie: `access_token=${token}` }, cache: "no-store" });
    if (!response.ok) return null;
    return response.json();
  } catch { return null; }
}

export default async function WorkspacePage() {
  const user = await getUser();
  if (!user) redirect("/login");
  return <main className="workspace"><header className="workspace-nav"><Link className="brand" href="/">Scholar<span>Signal</span></Link><div><Link className="text-link" href="/search">Search papers</Link><span className="user-chip">{user.display_name}</span><LogoutButton /></div></header><section className="workspace-body"><p className="eyebrow"><span className="status-dot" /> YOUR RESEARCH DESK</p><h1>Good to have you here,<br /><em>{user.display_name}.</em></h1><p className="intro">Search ingested OpenAlex publications with lexical matching or semantic similarity.</p><Link className="button button-dark search-cta" href="/search">Search publications <span aria-hidden="true">↗</span></Link><div className="empty-research"><span className="empty-glyph">✳</span><div><h2>A thoughtful beginning.</h2><p>Saved papers and personal interests are planned for later milestones.</p></div><span className="milestone-tag">MILESTONE 2 · SEARCH</span></div></section><footer className="landing-footer"><span>Signed in as {user.email}</span><span>ScholarSignal · Research, connected.</span></footer></main>;
}

