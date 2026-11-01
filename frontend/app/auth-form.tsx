"use client";

import Link from "next/link";
import { type FormEvent, useRef, useState } from "react";
import { useRouter } from "next/navigation";

type Props = { mode: "login" | "register" };

function getErrorMessage(payload: unknown, status: number, mode: Props["mode"]): string {
  if (payload && typeof payload === "object" && "detail" in payload) {
    const detail = payload.detail;
    if (typeof detail === "string" && detail.trim()) return detail;
  }
  if (status === 401) return "Email or password is incorrect.";
  if (status === 422) {
    return mode === "login"
      ? "Please enter a valid email address and password."
      : "Please check your name, email address, and password.";
  }
  if (status === 429) {
    return mode === "login"
      ? "Too many sign-in attempts. Please wait a moment and try again."
      : "Too many account creation attempts. Please wait a moment and try again.";
  }
  if (status >= 500) {
    return mode === "login"
      ? "The sign-in service is temporarily unavailable. Please try again shortly."
      : "Account creation is temporarily unavailable. Please try again shortly.";
  }
  return mode === "login"
    ? "We couldn’t sign you in. Please try again."
    : "We couldn’t create your account. Please try again.";
}

export function AuthForm({ mode }: Props) {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const submissionInProgress = useRef(false);
  const router = useRouter();
  const register = mode === "register";

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submissionInProgress.current) return;
    submissionInProgress.current = true;
    setError("");
    setBusy(true);
    const form = new FormData(event.currentTarget);
    const payload = Object.fromEntries(form.entries());
    try {
      const response = await fetch(`/api/v1/auth/${mode}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify(payload),
      });
      const responseText = await response.text();
      let body: unknown;
      if (responseText) {
        try {
          body = JSON.parse(responseText);
        } catch {
          body = undefined;
        }
      }
      if (!response.ok) throw new Error(getErrorMessage(body, response.status, mode));
      router.push("/workspace");
      router.refresh();
    } catch (cause) {
      setError(
        cause instanceof TypeError
          ? "Unable to reach the application service. Check your connection and try again."
          : cause instanceof Error && cause.message
            ? cause.message
            : "Unable to contact the application service. Check your connection and try again.",
      );
    } finally {
      submissionInProgress.current = false;
      setBusy(false);
    }
  }

  return (
    <main className="auth-page">
      <Link className="brand" href="/">
        Scholar<span>Signal</span>
      </Link>
      <section className="auth-panel">
        <p className="eyebrow">{register ? "A clearer view of the literature" : "Welcome back"}</p>
        <h1>{register ? "Begin with a question." : "Pick up where you left off."}</h1>
        <p className="auth-copy">
          {register
            ? "Create a private research workspace. Your interests and reading history stay yours."
            : "Sign in to return to your research workspace."}
        </p>
        <form onSubmit={submit} className="auth-form">
          {register && (
            <label>
              Your name
              <input name="display_name" autoComplete="name" required minLength={1} maxLength={80} />
            </label>
          )}
          <label>
            Email address
            <input name="email" type="email" autoComplete="email" required maxLength={320} />
          </label>
          <label>
            Password
            <input
              name="password"
              type="password"
              autoComplete={register ? "new-password" : "current-password"}
              required
              minLength={register ? 12 : 1}
              maxLength={128}
            />
            {register && <small>Use at least 12 characters.</small>}
          </label>
          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}
          <button
            type="submit"
            disabled={busy}
            aria-busy={busy}
            className="button button-dark form-submit"
          >
            {busy
              ? register
                ? "Creating account…"
                : "Signing in…"
              : register
                ? "Create your account"
                : "Log in"}
            <span aria-hidden="true">↗</span>
          </button>
        </form>
        <p className="switch-auth">
          {register ? "Already have a workspace? " : "New to ScholarSignal? "}
          <Link href={register ? "/login" : "/register"}>
            {register ? "Log in" : "Create an account"}
          </Link>
        </p>
        <p className="privacy-note">Your account is secured with a private, encrypted session.</p>
      </section>
    </main>
  );
}
