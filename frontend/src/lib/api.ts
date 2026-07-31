// Typed client for the Club & Event Concierge FastAPI backend.

import type { CampusFilter, ChatResponse, EventSearchResult } from "@/types";

const BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export interface ChatParams {
  query: string;
  campus: CampusFilter;
  freeFoodOnly: boolean;
  interests?: string[];
  history?: { role: "user" | "bot"; content: string }[];
}

export async function sendChat(params: ChatParams): Promise<ChatResponse> {
  const response = await fetch(`${BASE_URL}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      query: params.query,
      campus: params.campus,
      free_food_only: params.freeFoodOnly,
      interests: params.interests ?? [],
      history: params.history ?? [],
    }),
  });
  if (!response.ok) {
    throw new Error(`Backend error ${response.status}`);
  }
  return (await response.json()) as ChatResponse;
}

export async function fetchUpcoming(
  campus: string,
  limit = 12,
  interests: string[] = [],
): Promise<EventSearchResult[]> {
  const params = new URLSearchParams({ campus, limit: String(limit) });
  if (interests.length) params.set("interests", interests.join(","));
  const response = await fetch(`${BASE_URL}/events/upcoming?${params}`);
  if (!response.ok) {
    throw new Error(`Upcoming fetch failed ${response.status}`);
  }
  const data = (await response.json()) as { results: EventSearchResult[] };
  return data.results;
}

export async function seedDemo(): Promise<{ seeded: number }> {
  const response = await fetch(`${BASE_URL}/admin/seed`, { method: "POST" });
  if (!response.ok) {
    throw new Error(`Seed failed ${response.status}`);
  }
  return (await response.json()) as { seeded: number };
}

export interface IngestStats {
  scraped: number;
  skipped_not_free: number;
  duplicates: number;
  failed: number;
  inserted: number;
}

export async function runIngestion(): Promise<IngestStats> {
  const response = await fetch(`${BASE_URL}/admin/ingest`, { method: "POST" });
  if (!response.ok) {
    throw new Error(`Ingestion failed ${response.status}`);
  }
  return (await response.json()) as IngestStats;
}

export interface UserPublic {
  id: string;
  email: string;
  name: string;
  campus: string | null;
  program: string | null;
  interests: string[];
}

export interface AuthResult {
  token: string;
  user: UserPublic;
}

async function authRequest(path: string, body: object): Promise<AuthResult> {
  const response = await fetch(`${BASE_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const detail = await response
      .json()
      .then((d) => d.detail as string)
      .catch(() => null);
    throw new Error(detail ?? `Request failed (${response.status})`);
  }
  return (await response.json()) as AuthResult;
}

export function login(email: string, password: string): Promise<AuthResult> {
  return authRequest("/auth/login", { email, password });
}

export function register(
  name: string,
  email: string,
  password: string,
): Promise<AuthResult> {
  return authRequest("/auth/register", { name, email, password });
}

export function googleLogin(credential: string): Promise<AuthResult> {
  return authRequest("/auth/google", { credential });
}

export async function updateProfile(
  token: string,
  profile: {
    name: string;
    campus: string | null;
    program: string | null;
    interests: string[];
  },
): Promise<UserPublic> {
  const response = await fetch(`${BASE_URL}/auth/profile`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(profile),
  });
  if (!response.ok) {
    throw new Error(`Profile update failed (${response.status})`);
  }
  return (await response.json()) as UserPublic;
}

export async function resetIngested(): Promise<{ reset: boolean }> {
  const response = await fetch(`${BASE_URL}/admin/reset-ingested`, {
    method: "POST",
  });
  if (!response.ok) {
    throw new Error(`Reset failed ${response.status}`);
  }
  return (await response.json()) as { reset: boolean };
}
