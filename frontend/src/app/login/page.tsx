"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { login, register, googleLogin } from "@/lib/api";
import { saveSession } from "@/lib/auth";

type Mode = "signin" | "signup";

const GOOGLE_CLIENT_ID = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID;

declare global {
  interface Window {
    google?: any;
  }
}

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("signin");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const googleRef = useRef<HTMLDivElement>(null);
  const gbtnRef = useRef<HTMLDivElement>(null);

  function switchMode(next: Mode) {
    setMode(next);
    setError("");
  }

  // Load Google Identity Services and render the (invisible) real button, laid
  // over our own styled button so the secure Google flow still handles clicks.
  useEffect(() => {
    if (!GOOGLE_CLIENT_ID) return;

    // Size Google's hidden widget to fully cover our custom button so a click
    // anywhere on it triggers the sign-in. GIS caps button width at 400px, so
    // we render at the capped width and scale the overlay to fill.
    function fitOverlay() {
      const host = gbtnRef.current;
      const overlay = googleRef.current;
      if (!host || !overlay) return;
      const w = host.offsetWidth || 360;
      const h = host.offsetHeight || 56;
      const rendered = overlay.firstElementChild as HTMLElement | null;
      const rw = rendered?.offsetWidth || Math.min(w, 400);
      const rh = rendered?.offsetHeight || 44;
      overlay.style.transform = `scale(${w / rw}, ${h / rh})`;
    }

    const script = document.createElement("script");
    script.src = "https://accounts.google.com/gsi/client";
    script.async = true;
    script.onload = () => {
      if (!window.google || !googleRef.current) return;
      window.google.accounts.id.initialize({
        client_id: GOOGLE_CLIENT_ID,
        callback: async (resp: { credential: string }) => {
          try {
            const result = await googleLogin(resp.credential);
            saveSession({ token: result.token, user: result.user });
            router.replace("/");
          } catch (e) {
            setError(e instanceof Error ? e.message : "Google sign-in failed");
          }
        },
      });
      window.google.accounts.id.renderButton(googleRef.current, {
        theme: "filled_black",
        size: "large",
        shape: "pill",
        width: Math.min(gbtnRef.current?.offsetWidth || 360, 400),
        text: "continue_with",
        logo_alignment: "center",
      });
      // Fit once the iframe has laid out, and again on resize.
      requestAnimationFrame(fitOverlay);
      setTimeout(fitOverlay, 300);
    };
    document.body.appendChild(script);
    window.addEventListener("resize", fitOverlay);
    return () => {
      script.remove();
      window.removeEventListener("resize", fitOverlay);
    };
  }, [router]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (busy) return;
    setError("");
    setBusy(true);
    try {
      const result =
        mode === "signup"
          ? await register(name, email, password)
          : await login(email, password);
      saveSession({ token: result.token, user: result.user });
      router.replace("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
      setBusy(false);
    }
  }

  return (
    <main className="auth-split">
      <section className="auth-brand">
        <div className="brand">
          <span className="brand-mark">C</span> Club &amp; Event Concierge
        </div>

        <div className="auth-brand-center">
          <h1>
            Every campus event.
            <br />
            <span className="grad-text">One conversation.</span>
          </h1>
          <p>
            A concierge that reads campus calendars and club Instagram flyers
            for you — then answers in plain English, grounded only in real,
            verified events.
          </p>

          <div className="auth-feats">
            <div className="auth-feat">
              <span className="feat-ic">🛰️</span>
              <span>
                <b>Live across four schools.</b> UBC, SFU, BCIT and Douglas —
                scraped from official calendars and club pages.
              </span>
            </div>
            <div className="auth-feat">
              <span className="feat-ic">🖼️</span>
              <span>
                <b>Reads the flyers.</b> Instagram poster images become
                searchable events automatically.
              </span>
            </div>
            <div className="auth-feat">
              <span className="feat-ic">🛡️</span>
              <span>
                <b>Never makes it up.</b> Every answer links back to the
                official event page.
              </span>
            </div>
          </div>
        </div>

        <div className="auth-stats">
          <div className="auth-stat">
            <div className="n">4</div>
            <div className="l">campuses live</div>
          </div>
          <div className="auth-stat">
            <div className="n">20+</div>
            <div className="l">sources &amp; clubs</div>
          </div>
          <div className="auth-stat">
            <div className="n">0</div>
            <div className="l">made-up events</div>
          </div>
        </div>
      </section>

      <section className="auth-form-side">
        <form className="auth-card" onSubmit={submit}>
          <h2>{mode === "signin" ? "Welcome back" : "Get started"}</h2>
          <p className="sub">
            {mode === "signin"
              ? "Sign in to your concierge."
              : "Create a free account — it takes twenty seconds."}
          </p>

          <div className="mode-row">
            <button
              type="button"
              className={mode === "signin" ? "active" : ""}
              onClick={() => switchMode("signin")}
            >
              Sign in
            </button>
            <button
              type="button"
              className={mode === "signup" ? "active" : ""}
              onClick={() => switchMode("signup")}
            >
              Create account
            </button>
          </div>

          {GOOGLE_CLIENT_ID && (
            <>
              <div className="gbtn" ref={gbtnRef}>
                <svg className="gbtn-logo" viewBox="0 0 48 48" aria-hidden="true">
                  <path
                    fill="#EA4335"
                    d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"
                  />
                  <path
                    fill="#4285F4"
                    d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"
                  />
                  <path
                    fill="#FBBC05"
                    d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"
                  />
                  <path
                    fill="#34A853"
                    d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"
                  />
                </svg>
                <span className="gbtn-label">Continue with Google</span>
                <div ref={googleRef} className="gbtn-overlay" />
              </div>
              <div className="or-divider">
                <span>or</span>
              </div>
            </>
          )}

          {mode === "signup" && (
            <div className="field">
              <label htmlFor="name">Full name</label>
              <input
                id="name"
                type="text"
                value={name}
                placeholder="Alex Chen"
                autoComplete="name"
                onChange={(e) => setName(e.target.value)}
                required
              />
            </div>
          )}
          <div className="field">
            <label htmlFor="email">Email address</label>
            <input
              id="email"
              type="email"
              value={email}
              placeholder="you@campus.ca"
              autoComplete="email"
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </div>
          <div className="field">
            <label htmlFor="password">
              {mode === "signup" ? "Password (8+ characters)" : "Password"}
            </label>
            <input
              id="password"
              type="password"
              value={password}
              placeholder="••••••••••"
              minLength={mode === "signup" ? 8 : undefined}
              autoComplete={
                mode === "signup" ? "new-password" : "current-password"
              }
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>

          <button className="primary-btn" type="submit" disabled={busy}>
            {busy
              ? "One moment…"
              : mode === "signin"
                ? "Sign in"
                : "Create account"}
          </button>

          {error && <div className="login-err">{error}</div>}
        </form>
      </section>
    </main>
  );
}
