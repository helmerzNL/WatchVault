import { api } from "./api";

// Batches title ids that scroll into view and asks the backend to enrich any
// that still lack metadata. The backend filters already-enriched ids and
// de-duplicates jobs, so we only need light client-side throttling.
const requested = new Set<string>();
let pending = new Set<string>();
let timer: number | undefined;

function flush() {
  const ids = Array.from(pending);
  pending = new Set();
  if (!ids.length) return;
  api.post("/titles/enrich-missing", { ids }).catch(() => {});
}

export function enqueueEnrich(id?: string | null) {
  if (!id || requested.has(id)) return;
  requested.add(id);
  pending.add(id);
  if (timer) window.clearTimeout(timer);
  timer = window.setTimeout(flush, 700);
}
