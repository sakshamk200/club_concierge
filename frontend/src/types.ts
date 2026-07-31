// Shared types mirroring the backend Pydantic contracts.

export type CampusFilter = "UBC" | "SFU" | "BCIT" | "Douglas" | "All";

export interface EventSearchResult {
  id: string | null;
  title: string;
  organizer: string | null;
  location: string | null;
  campus: string | null;
  event_timestamp: string | null;
  registration_deadline: string | null;
  original_image_url: string | null;
  image_hash: string | null;
  has_free_food: boolean;
  perks: string[];
  similarity: number;
}

export interface UnderstoodIntent {
  campus: string | null;
  time_label: string | null;
  free_food: boolean;
  topic: string | null;
}

export interface ChatResponse {
  query: string;
  campus: CampusFilter;
  free_food_only: boolean;
  answer: string;
  results: EventSearchResult[];
  understood?: UnderstoodIntent;
}
