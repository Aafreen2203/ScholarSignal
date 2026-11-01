"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

export function LogoutButton() {
  const router = useRouter();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function logout() {
    setBusy(true);
    setError("");
    try {
      const response = await fetch("/api/v1/auth/logout", { method: "POST" });
      if (!response.ok) throw new Error("Unable to log out. Please try again.");
      router.replace("/login");
      router.refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to log out. Please try again.");
      setBusy(false);
    }
  }

  return <span><button className="text-button" type="button" onClick={logout} disabled={busy}>{busy ? "Logging out…" : "Log out"}</button>{error && <span role="alert">{error}</span>}</span>;
}
