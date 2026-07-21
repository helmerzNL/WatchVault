export const FIXED_NOW = "2026-07-21T12:00:00.000Z";
export const FIXED_DATE = "2026-07-21";
export const FIXED_MONTH = "2026-07";
export const USER_ID = "profile-synthetic";
export const TITLE_ID = "title-synthetic-film";

export const PROFILE = {
  id: USER_ID,
  name: "Synthetic Viewer",
  display_name: "Synthetic Viewer",
  household_id: "household-synthetic",
  is_admin: true,
  permissions: ["catalog.read", "ingest.write"],
};

export const PROVIDER = {
  id: "synthetic-stream",
  key: "synthetic-stream",
  name: "Synthetic Stream",
  color: "#6750a4",
};

export const TITLE = {
  id: TITLE_ID,
  title: "Synthetic Film",
  original_title: "Synthetic Film",
  year: 2026,
  kind: "movie",
  overview: "A deterministic film used only by the browser evidence suite.",
  runtime: 118,
  poster: null,
  backdrop: null,
  genres: ["Drama"],
  providers: [PROVIDER.id],
  watch_dates: [] as string[],
};

export const SEARCH_RESULT = {
  ...TITLE,
  platforms: [PROVIDER.id],
  watch_count: 0,
  tags: ["Reference"],
};

export const BASE_PREFERENCES = {
  theme: "dark",
  accent: "#006dcc",
  language: "en",
  expert: false,
  default_profile: USER_ID,
  dashboard_layout: { order: [], hidden: [], stats: { order: [], hidden: [] } },
};

export const BASE_SUMMARY = {
  totals: {
    hours: 2,
    titles: 1,
    movies: 1,
    episodes: 0,
    remaining_minutes: 0,
    remaining_items: 0,
  },
  this_month: { hours: 2, events: 1 },
  events: [{ date: "2026-07-14", count: 1 }],
};

export const BASE_MONTHLY_TITLE = {
  id: "title-existing-film",
  title: "Existing Film",
  year: 2025,
  kind: "movie",
  poster: null,
  watched_at: "2026-07-14",
  provider: PROVIDER.id,
};
