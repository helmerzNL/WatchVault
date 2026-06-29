import { useEffect, useMemo, useState } from "react";
import { useApp } from "../lib/app";
import { api } from "../lib/api";
import { Loading, Empty, Poster, ErrorState } from "../components/ui";
import { IconSearch } from "../components/icons";
import { fmtHours, fmtDate } from "../lib/format";

interface Provider { key: string; name: string; }

export function Search() {
  const { scope } = useApp();
  const [q, setQ] = useState("");
  const [genre, setGenre] = useState("");
  const [actor, setActor] = useState("");
  const [platform, setPlatform] = useState("");
  const [year, setYear] = useState("");
  const [kind, setKind] = useState("");
  const [providers, setProviders] = useState<Provider[]>([]);

  const [results, setResults] = useState<any[] | null>(null);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => { api.get("/providers").then(setProviders).catch(() => {}); }, []);

  const params = useMemo(() => ({ profile: scope, q, genre, actor, platform, year, kind }),
    [scope, q, genre, actor, platform, year, kind]);

  // debounced search
  useEffect(() => {
    const hasFilter = q || genre || actor || platform || year || kind;
    const t = setTimeout(async () => {
      setLoading(true); setError(null);
      try {
        const res = await api.get("/search", params);
        setResults(res.results); setTotal(res.total);
      } catch (e) { setError(e); } finally { setLoading(false); }
    }, hasFilter ? 280 : 0);
    return () => clearTimeout(t);
  }, [params]);

  const activeFilters = [genre, actor, platform, year, kind].filter(Boolean).length;

  function clearAll() {
    setQ(""); setGenre(""); setActor(""); setPlatform(""); setYear(""); setKind("");
  }

  return (
    <>
      <h1 className="large-title" style={{ marginBottom: 16 }}>Search</h1>

      <div className="card" style={{ marginBottom: 20 }}>
        <div className="row" style={{ gap: 10, marginBottom: 14 }}>
          <IconSearch width={20} height={20} className="muted" />
          <input value={q} onChange={(e) => setQ(e.target.value)} autoFocus
            placeholder="Search titles, genres, actors…" style={{ border: "none", minHeight: 32, padding: 0, background: "transparent" }} />
        </div>
        <hr className="divider" style={{ margin: "0 0 14px" }} />
        <div className="filters-grid">
          <div>
            <label>Type</label>
            <select value={kind} onChange={(e) => setKind(e.target.value)}>
              <option value="">All</option>
              <option value="movie">Movies</option>
              <option value="series">Series</option>
            </select>
          </div>
          <div>
            <label>Platform</label>
            <select value={platform} onChange={(e) => setPlatform(e.target.value)}>
              <option value="">Any</option>
              {providers.map((p) => <option key={p.key} value={p.key}>{p.name}</option>)}
            </select>
          </div>
          <div>
            <label>Genre</label>
            <input value={genre} onChange={(e) => setGenre(e.target.value)} placeholder="e.g. Sci-Fi" />
          </div>
          <div>
            <label>Actor</label>
            <input value={actor} onChange={(e) => setActor(e.target.value)} placeholder="e.g. Pedro Pascal" />
          </div>
          <div>
            <label>Year</label>
            <input value={year} onChange={(e) => setYear(e.target.value.replace(/\D/g, ""))} placeholder="2025"
              inputMode="numeric" maxLength={4} />
          </div>
        </div>
        {activeFilters > 0 && (
          <div className="row" style={{ marginTop: 14 }}>
            <span className="caption">{activeFilters} filter{activeFilters > 1 ? "s" : ""} active</span>
            <div className="spacer" />
            <button className="btn-ghost btn-sm" onClick={clearAll}>Clear filters</button>
          </div>
        )}
      </div>

      {loading && !results ? <Loading /> :
        error ? <ErrorState error={error} /> :
        results === null ? (
          <Empty title="Search your vault" hint="Find anything you've watched — combine filters like 'Sci-Fi series on Netflix in 2025'." />
        ) : results.length === 0 ? (
          <Empty title="No matches" hint="Try fewer or different filters." />
        ) : (
          <>
            <p className="muted" style={{ marginBottom: 14 }}>{total} title{total !== 1 ? "s" : ""}</p>
            <div className="poster-grid">
              {results.map((t) => (
                <Poster key={t.id} to={`/title/${t.id}`} poster={t.poster} title={t.title} kind={t.kind}
                  badge={t.kind === "movie" ? "Film" : "Series"}
                  subtitle={`${t.platforms?.[0] || ""}${t.last_watched ? " · " + fmtDate(t.last_watched) : ""}`} />
              ))}
            </div>
          </>
        )}
    </>
  );
}
