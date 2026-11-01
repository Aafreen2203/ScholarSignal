import Link from "next/link";

export default function Home() {
  return <main className="landing">
    <nav className="topbar"><Link className="brand" href="/">Scholar<span>Signal</span></Link><div className="navlinks"><Link href="/login">Log in</Link><Link className="button button-dark" href="/register">Create account <span aria-hidden="true">↗</span></Link></div></nav>
    <section className="hero"><p className="eyebrow"><span className="status-dot" /> A workspace for the curious</p><h1>Find the paper<br />that changes <em>everything.</em></h1><p className="intro">Scientific discovery moves through connections. ScholarSignal helps you find the work, ideas, and people that move yours forward.</p><div className="hero-actions"><Link className="button button-dark" href="/register">Start exploring <span aria-hidden="true">↗</span></Link><Link className="text-link" href="/login">I already have an account</Link></div><div className="proof"><span className="proof-line" /><span>Built for research, grounded in evidence</span></div></section>
    <aside className="side-note"><span className="note-index">01 — THE QUESTION</span><p>What if your next great idea was already waiting in a paper you hadn’t found yet?</p><span className="note-mark">✳</span></aside>
    <footer className="landing-footer"><span>ScholarSignal <span className="muted">· Research, connected.</span></span><span>Independent scientific discovery</span></footer>
  </main>;
}

