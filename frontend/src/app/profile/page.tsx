"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { updateProfile } from "@/lib/api";
import { clearSession, getSession, saveSession } from "@/lib/auth";

const CAMPUSES = ["UBC", "SFU", "BCIT", "Douglas"];

export default function ProfilePage() {
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [campus, setCampus] = useState<string | null>(null);
  const [program, setProgram] = useState("");
  const [interests, setInterests] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const session = getSession();
    if (!session) {
      router.replace("/login");
      return;
    }
    const u = session.user;
    setEmail(u.email);
    setName(u.name);
    setCampus(u.campus);
    setProgram(u.program ?? "");
    setInterests(u.interests.join(", "));
    setReady(true);
  }, [router]);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    const session = getSession();
    if (!session || busy) return;
    setBusy(true);
    setMsg("");
    try {
      const user = await updateProfile(session.token, {
        name,
        campus,
        program: program.trim() || null,
        interests: interests
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
      });
      saveSession({ token: session.token, user });
      setMsg("Saved ✓");
    } catch {
      setMsg("Save failed — try again");
    } finally {
      setBusy(false);
      setTimeout(() => setMsg(""), 2500);
    }
  }

  function logout() {
    clearSession();
    router.replace("/login");
  }

  if (!ready) return null;

  return (
    <>
      <nav className="nav">
        <div className="nav-inner">
          <div className="brand">
            <span className="brand-mark">C</span> Club &amp; Event Concierge
          </div>
          <div className="nav-right">
            <button className="ghost-btn" onClick={() => router.push("/")}>
              ← Back to events
            </button>
            <button className="ghost-btn" onClick={logout}>
              Sign out
            </button>
          </div>
        </div>
      </nav>

      <main className="profile-shell">
        <form className="auth-card" onSubmit={save}>
          <h2>Your profile</h2>
          <p className="sub">{email}</p>

          <div className="field">
            <label htmlFor="name">Full name</label>
            <input
              id="name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
            />
          </div>

          <div className="field">
            <label>Home campus</label>
            <div className="mode-row" style={{ marginBottom: 0 }}>
              {CAMPUSES.map((c) => (
                <button
                  key={c}
                  type="button"
                  className={campus === c ? "active" : ""}
                  onClick={() => setCampus(campus === c ? null : c)}
                >
                  {c}
                </button>
              ))}
            </div>
          </div>

          <div className="field">
            <label htmlFor="program">Program</label>
            <input
              id="program"
              type="text"
              value={program}
              placeholder="e.g. Computer Science"
              onChange={(e) => setProgram(e.target.value)}
            />
          </div>

          <div className="field">
            <label htmlFor="interests">Interests (comma-separated)</label>
            <input
              id="interests"
              type="text"
              value={interests}
              placeholder="career fairs, free food, hackathons"
              onChange={(e) => setInterests(e.target.value)}
            />
          </div>

          <button className="primary-btn" type="submit" disabled={busy}>
            {busy ? "Saving…" : msg || "Save profile"}
          </button>

          <div className="auth-fineprint">
            Preferences will personalise your recommendations as
            preference-aware ranking lands in the next milestone.
          </div>
        </form>
      </main>
    </>
  );
}
