"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";

type Props = { mode: "login" | "register" };

export function AuthForm({ mode }: Props) {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const router = useRouter();
  const register = mode === "register";

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError(""); setBusy(true);
    const form = new FormData(event.currentTarget);
    const payload = Object.fromEntries(form.entries());
    try {
      const response = await fetch(`/api/v1/auth/${mode}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail ?? "We couldn’t sign you in. Please try again.");
      router.push("/workspace"); router.refresh();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "A connection error occurred."); }
    finally { setBusy(false); }
  }

  return <main className="auth-page"><Link className="brand" href="/">Scholar<span>Signal</span></Link><section className="auth-panel"><p className="eyebrow">{register ? "A clearer view of the literature" : "Welcome back"}</p><h1>{register ? "Begin with a question." : "Pick up where you left off."}</h1><p className="auth-copy">{register ? "Create a private research workspace. Your interests and reading history stay yours." : "Sign in to return to your research workspace."}</p>
    <form onSubmit={submit} className="auth-form">{register && <label>Your name<input name="display_name" autoComplete="name" required minLength={1} maxLength={80} /></label>}<label>Email address<input name="email" type="email" autoComplete="email" required maxLength={320} /></label><label>Password<input name="password" type="password" autoComplete={register ? "new-password" : "current-password"} required minLength={register ? 12 : 1} maxLength={128} />{register && <small>Use at least 12 characters.</small>}</label>{error && <p className="form-error" role="alert">{error}</p>}<button disabled={busy} className="button button-dark form-submit">{busy ? "Please wait…" : register ? "Create your account" : "Log in"}<span aria-hidden="true">↗</span></button></form>
    <p className="switch-auth">{register ? "Already have a workspace? " : "New to ScholarSignal? "}<Link href={register ? "/login" : "/register"}>{register ? "Log in" : "Create an account"}</Link></p><p className="privacy-note">Your account is secured with a private, encrypted session.</p></section></main>;
}

