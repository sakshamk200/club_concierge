"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { fetchUpcoming, runIngestion, sendChat } from "@/lib/api";
import { clearSession, getSession } from "@/lib/auth";
import type {
  CampusFilter,
  EventSearchResult,
  UnderstoodIntent,
} from "@/types";

interface Turn {
  role: "user" | "bot";
  text: string;
  results?: EventSearchResult[];
  understood?: UnderstoodIntent;
}

function understoodChips(u?: UnderstoodIntent): string[] {
  if (!u) return [];
  const chips: string[] = [];
  if (u.campus) chips.push(u.campus);
  if (u.time_label) chips.push(u.time_label);
  if (u.free_food) chips.push("🍕 free food");
  if (u.topic) chips.push(u.topic);
  return chips;
}

const CAMPUSES: CampusFilter[] = ["All", "UBC", "SFU", "BCIT", "Douglas"];

function formatWhen(iso: string | null): string {
  if (!iso) return "Time TBA";
  return new Date(iso).toLocaleString(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function daysAway(iso: string | null): string | null {
  if (!iso) return null;
  const ms = new Date(iso).getTime() - Date.now();
  const d = Math.round(ms / 86400000);
  if (d < 0) return null;
  if (d === 0) return "Today";
  if (d === 1) return "Tomorrow";
  if (d <= 7) return `In ${d} days`;
  return null;
}

function titleCase(s: string): string {
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : s;
}

function gcalStamp(d: Date): string {
  return d.toISOString().replace(/[-:]/g, "").replace(/\.\d{3}/, "");
}

function googleCalendarUrl(ev: EventSearchResult): string | null {
  if (!ev.event_timestamp) return null;
  const start = new Date(ev.event_timestamp);
  const end = new Date(start.getTime() + 2 * 60 * 60 * 1000); // default 2h
  const details = [
    ev.organizer ? `Organized by ${ev.organizer}.` : "",
    ev.original_image_url ? `Source: ${ev.original_image_url}` : "",
    "Added via Club & Event Concierge.",
  ]
    .filter(Boolean)
    .join("\n");
  const params = new URLSearchParams({
    action: "TEMPLATE",
    text: ev.title,
    dates: `${gcalStamp(start)}/${gcalStamp(end)}`,
    location: ev.location ?? "",
    details,
  });
  return `https://calendar.google.com/calendar/render?${params.toString()}`;
}

function matchedInterest(
  ev: EventSearchResult,
  interests: string[],
): string | null {
  if (!interests.length) return null;
  const hay = `${ev.title} ${ev.organizer ?? ""} ${ev.perks.join(" ")}`.toLowerCase();
  for (const raw of interests) {
    const term = raw.trim().toLowerCase();
    if (term && hay.includes(term)) return raw.trim();
  }
  return null;
}

function EventCard({
  ev,
  interests = [],
}: {
  ev: EventSearchResult;
  interests?: string[];
}) {
  const band = ev.campus ? ev.campus.toLowerCase() : "";
  const soon = daysAway(ev.event_timestamp);
  const fromInsta = ev.organizer?.startsWith("@");
  const calUrl = googleCalendarUrl(ev);
  const match = matchedInterest(ev, interests);
  return (
    <article className={`ecard${match ? " matched" : ""}`}>
      <div className={`ecard-band ${band}`} />
      <div className="ecard-body">
        <div className="ecard-top">
          {ev.campus && <span className="badge">{ev.campus}</span>}
          {match && (
            <span className="badge foryou" title={`Matches your interest: ${match}`}>
              ✨ {match}
            </span>
          )}
          {ev.has_free_food && <span className="badge food">🍕 Free food</span>}
          {soon && <span className="badge soon">{soon}</span>}
        </div>
        <h3>{ev.title}</h3>
        {ev.organizer && (
          <div className="ecard-org">
            <span className={`org-mark${fromInsta ? " insta" : ""}`}>
              {(ev.organizer.replace(/^@/, "").match(/[a-z0-9]/i)?.[0] ?? "•").toUpperCase()}
            </span>
            <span className="org-name">{ev.organizer}</span>
          </div>
        )}
        <div className="ecard-meta">
          <div className="meta-row">
            <span className="meta-ic" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none">
                <rect x="3" y="4.5" width="18" height="16" rx="3" />
                <path d="M3 9h18M8 2.5v4M16 2.5v4" />
              </svg>
            </span>
            <span className="meta-when">{formatWhen(ev.event_timestamp)}</span>
          </div>
          {ev.location && (
            <div className="meta-row">
              <span className="meta-ic" aria-hidden="true">
                <svg viewBox="0 0 24 24" fill="none">
                  <path d="M12 22c5-5 8-8.5 8-12a8 8 0 1 0-16 0c0 3.5 3 7 8 12Z" />
                  <circle cx="12" cy="10" r="2.6" />
                </svg>
              </span>
              <span className="meta-loc">{ev.location}</span>
            </div>
          )}
        </div>
        <div className="ecard-actions">
          {calUrl && (
            <a
              className="cal-btn"
              href={calUrl}
              target="_blank"
              rel="noreferrer"
            >
              📅 Add to calendar
            </a>
          )}
          {ev.original_image_url && (
            <a
              className="source-link"
              href={ev.original_image_url}
              target="_blank"
              rel="noreferrer"
            >
              {fromInsta ? "Instagram ↗" : "Source ↗"}
            </a>
          )}
        </div>
      </div>
    </article>
  );
}

const CATEGORIES = [
  { label: "🍕 Free food", q: "free food" },
  { label: "💼 Careers", q: "career fairs and job workshops" },
  { label: "🎉 Socials", q: "socials, clubs and parties" },
  { label: "🧠 Workshops", q: "workshops and skill sessions" },
  { label: "🏃 Active", q: "sports, fitness and yoga" },
  { label: "📅 This week", q: "what's happening this week" },
];

// Natural-language prompts that show off query understanding in a demo.
const SMART_PROMPTS = [
  "free pizza this weekend at SFU",
  "career stuff at BCIT this week",
  "something fun tonight",
  "live music before the weekend",
];

export default function Home() {
  const router = useRouter();
  const [authed, setAuthed] = useState(false);
  const [firstName, setFirstName] = useState("");
  const [interests, setInterests] = useState<string[]>([]);
  const [campus, setCampus] = useState<CampusFilter>("All");
  const [upcoming, setUpcoming] = useState<EventSearchResult[]>([]);
  const [loadingGrid, setLoadingGrid] = useState(true);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [thinking, setThinking] = useState(false);
  const [refreshMsg, setRefreshMsg] = useState("");
  const chatMode = turns.length > 0;
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const session = getSession();
    if (!session) {
      router.replace("/login");
      return;
    }
    setFirstName(titleCase(session.user.name.split(" ")[0]));
    setInterests(session.user.interests ?? []);
    // Default the grid to the student's home campus if they set one.
    const home = session.user.campus as CampusFilter | null;
    if (home && ["UBC", "SFU", "BCIT", "Douglas"].includes(home)) {
      setCampus(home);
    }
    setAuthed(true);
  }, [router]);

  const loadUpcoming = useCallback(
    async (c: CampusFilter, prefs: string[]) => {
      setLoadingGrid(true);
      try {
        setUpcoming(await fetchUpcoming(c, 12, prefs));
      } catch {
        setUpcoming([]);
      } finally {
        setLoadingGrid(false);
      }
    },
    [],
  );

  useEffect(() => {
    if (authed) void loadUpcoming(campus, interests);
  }, [authed, campus, interests, loadUpcoming]);

  async function ask(query: string) {
    const q = query.trim();
    if (!q || thinking) return;
    // Snapshot the conversation so far as history for follow-up context.
    const history = turns.map((t) => ({
      role: t.role,
      content: t.text,
    }));
    setTurns((t) => [...t, { role: "user", text: q }]);
    setInput("");
    setThinking(true);
    try {
      const res = await sendChat({
        query: q,
        campus,
        freeFoodOnly: false,
        interests,
        history,
      });
      setTurns((t) => [
        ...t,
        {
          role: "bot",
          text: res.answer,
          results: res.results,
          understood: res.understood,
        },
      ]);
    } catch {
      setTurns((t) => [
        ...t,
        {
          role: "bot",
          text: "I couldn't reach the concierge service — please try again in a moment.",
        },
      ]);
    } finally {
      setThinking(false);
      setTimeout(
        () => endRef.current?.scrollIntoView({ behavior: "smooth" }),
        80,
      );
    }
  }

  async function refresh() {
    setRefreshMsg("Scanning sources…");
    try {
      const s = await runIngestion();
      setRefreshMsg(`+${s.inserted} new · ${s.duplicates} known`);
      void loadUpcoming(campus, interests);
    } catch {
      setRefreshMsg("Refresh failed");
    }
    setTimeout(() => setRefreshMsg(""), 4000);
  }

  function logout() {
    clearSession();
    router.replace("/login");
  }

  if (!authed) return null;

  return (
    <>
      <nav className="nav">
        <div className="nav-inner">
          <div className="brand">
            <span className="brand-mark">C</span> Club &amp; Event Concierge
          </div>
          <div className="nav-right">
            <button className="ghost-btn" onClick={refresh}>
              {refreshMsg || "Refresh events"}
            </button>
            <button
              className="avatar-btn"
              onClick={() => router.push("/profile")}
            >
              <span className="avatar">{firstName.charAt(0) || "S"}</span>
              {firstName || "Profile"}
            </button>
            <button className="ghost-btn" onClick={logout}>
              Sign out
            </button>
          </div>
        </div>
      </nav>

      <main className="shell">
        {!chatMode && (
          <>
            <section className="hero">
              <div className="hero-eyebrow">
                <span className="live-dot" aria-hidden="true" />
                Live across UBC · SFU · BCIT · Douglas
              </div>
              <h1>
                What&apos;s happening
                <br />
                <span className="grad-text">on campus, {firstName}?</span>
              </h1>
              <p>
                Ask in plain English. The concierge searches real events scraped
                from campus calendars and club Instagram flyers — and never
                makes one up.
              </p>

              <div className="search-console">
                <div className="askbar">
                  <span className="askbar-ic" aria-hidden="true">
                    <svg viewBox="0 0 24 24" fill="none">
                      <circle cx="11" cy="11" r="7" />
                      <path d="m20 20-3.2-3.2" />
                    </svg>
                  </span>
                  <input
                    value={input}
                    placeholder="Try “free pizza this week” or “career fairs”…"
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") ask(input);
                    }}
                  />
                  {input.trim() && <kbd className="kbd-hint">↵</kbd>}
                  <button
                    disabled={thinking || !input.trim()}
                    onClick={() => ask(input)}
                  >
                    Ask
                  </button>
                </div>
                <div className="cat-row">
                  {CATEGORIES.map((c) => (
                    <button
                      key={c.label}
                      className="cat-chip"
                      onClick={() => ask(c.q)}
                    >
                      {c.label}
                    </button>
                  ))}
                </div>
              </div>

              <div className="try-row">
                <span className="try-label">Try asking</span>
                {SMART_PROMPTS.map((p) => (
                  <button
                    key={p}
                    className="try-chip"
                    onClick={() => ask(p)}
                  >
                    “{p}”
                  </button>
                ))}
              </div>
            </section>

            <section>
              <div className="section-head">
                <h2>Upcoming events</h2>
                <span className="count">
                  {loadingGrid ? "loading…" : `${upcoming.length} listed`}
                </span>
                <div className="right">
                  <div className="segment">
                    {CAMPUSES.map((c) => (
                      <button
                        key={c}
                        className={campus === c ? "active" : ""}
                        onClick={() => setCampus(c)}
                      >
                        {c}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              {interests.length > 0 ? (
                <div className="pref-bar">
                  <span className="pref-spark">✨</span>
                  <span className="pref-lead">Ranked for you —</span>
                  <div className="pref-chips">
                    {interests.slice(0, 6).map((i) => (
                      <span key={i} className="pref-chip">
                        {i}
                      </span>
                    ))}
                  </div>
                  <button
                    className="pref-edit"
                    onClick={() => router.push("/profile")}
                  >
                    Edit
                  </button>
                </div>
              ) : (
                <div className="pref-bar cta">
                  <span className="pref-lead">
                    💡 Tell us what you like and we&apos;ll rank events for you.
                  </span>
                  <button
                    className="pref-edit primary"
                    onClick={() => router.push("/profile")}
                  >
                    Set your interests →
                  </button>
                </div>
              )}

              {loadingGrid ? (
                <div className="empty">Loading the latest events…</div>
              ) : upcoming.length === 0 ? (
                <div className="empty">
                  No upcoming events for this campus right now.
                  <br />
                  Try another campus or hit “Refresh events”.
                </div>
              ) : (
                <div className="event-grid">
                  {upcoming.map((ev, i) => (
                    <EventCard ev={ev} interests={interests} key={ev.id ?? i} />
                  ))}
                </div>
              )}
            </section>
          </>
        )}

        {chatMode && (
          <div className="chat-wrap">
            <button className="back-btn" onClick={() => setTurns([])}>
              ← Back to browse
            </button>
            <div className="chat">
              {turns.map((turn, i) => (
                <div
                  key={i}
                  style={{ display: "flex", flexDirection: "column", gap: 14 }}
                >
                  {turn.role === "bot" &&
                    understoodChips(turn.understood).length > 0 && (
                      <div className="understood">
                        <span className="understood-label">Understood</span>
                        {understoodChips(turn.understood).map((c) => (
                          <span key={c} className="understood-chip">
                            {c}
                          </span>
                        ))}
                      </div>
                    )}
                  <div className={`bubble ${turn.role}`}>{turn.text}</div>
                  {turn.results && turn.results.length > 0 && (
                    <div className="event-grid">
                      {turn.results.map((ev, j) => (
                        <EventCard ev={ev} interests={interests} key={ev.id ?? j} />
                      ))}
                    </div>
                  )}
                </div>
              ))}
              {thinking && (
                <div className="typing">
                  <i />
                  <i />
                  <i />
                </div>
              )}
              <div ref={endRef} style={{ height: 90 }} />
            </div>
            <div className="composer-wrap">
              <div className="composer">
                <input
                  value={input}
                  placeholder="Ask a follow-up…"
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") ask(input);
                  }}
                />
                <button
                  disabled={thinking || !input.trim()}
                  onClick={() => ask(input)}
                >
                  Send
                </button>
              </div>
            </div>
          </div>
        )}
      </main>
    </>
  );
}
