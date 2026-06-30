import { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useApp } from "../lib/app";
import { useT, providerLabel } from "../lib/i18n";
import { api } from "../lib/api";
import { Loading, Empty, Poster, ErrorState } from "../components/ui";
import { IconSearch } from "../components/icons";
import { fmtHours, fmtDate } from "../lib/format";

interface Provider { key: string; name: string; }

const PAGE = 60;

export function Search() {
  const { scope } = useApp();
  const { t, lang } = useT();
  const [searchParams, setSearchParams] = useSearchParams();
  const [q, setQ] = useState(() => searchParams.get("q") || "");
  const [genre, setGenre] = useState(() => searchParams.get("genre") || "");
  const [actor, setActor] = useState(() => searchParams.get("actor") || "");
  const [platform, setPlatform] = useState(() => searchParams.get("platform") || "");
  const [year, setYear] = useState(() => searchParams.get("year") || "");
  const [kind, setKind] = useState(() => searchParams.get("kind") || "");
  const [providers, setProviders] = useState<Provider[]>([]);

  const [results, setResults] = useState<any[] | null>(null);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<unknown>(null);
  // Bumped on every filter-driven (page-0) reload so an in-flight loadMore from a
  // previous filter set can detect it is stale and drop its appended results.
  const reqRef = useRef(0);

  useEffect(() => { api.get("/providers").then(setProviders).catch(() => {}); }, []);

  // Persist active filters in the URL so they survive opening an item and
  // navigating back (the component remounts and re-reads from the URL).
  useEffect(() => {
    const next: Record<string, string> = {};
    if (q) next.q = q;
    if (genre) next.genre = genre;
    if (actor) next.actor = actor;
    if (platform) next.platform = platform;
    if (year) next.year = year;
    if (kind) next.kind = kind;
    setSearchParams(next, { replace: true });
  }, [q, genre, actor, platform, year, kind, setSearchParams]);

  const params = useMemo(() => ({ profile: scope, q, genre, actor, platform, year, kind, lang }),
    [scope, q, genre, actor, platform, year, kind, lang]);

  // Plex + Jellyfin are presented as one "Digital Library" option; selecting it
  // filters on either (the backend expands the `digital_library` key).
  const platformOptions = useMemo(() => {
    const out: { key: string; label: string }[] = [];
    let digital = false;
    for (const p of providers) {
      if (p.key === "plex" || p.key === "jellyfin") {
        if (digital) continue;
        digital = true;
        out.push({ key: "digital_library", label: providerLabel(t, "digital_library", p.name) });
      } else {
        out.push({ key: p.key, label: providerLabel(t, p.key, p.name) });
      }
    }
    return out;
  }, [providers, t]);

  // debounced page-0 (re)load whenever filters change
  useEffect(() => {
    const hasFilter = q || genre || actor || platform || year || kind;
    const id = ++reqRef.current;
    const handle = setTimeout(async () => {
      setLoading(true); setError(null);
      try {
        const res = await api.get("/search", { ...params, limit: PAGE, offset: 0 });
        if (reqRef.current !== id) return;
        setResults(res.results); setTotal(res.total);
      } catch (e) {
        if (reqRef.current === id) setError(e);
      } finally {
        if (reqRef.current === id) setLoading(false);
      }
    }, hasFilter ? 280 : 0);
    return () => clearTimeout(handle);
  }, [params]);

  async function loadMore() {
    if (loadingMore || loading || !results) return;
    const id = reqRef.current;
    const offset = results.length;
    setLoadingMore(true);
    try {
      const res = await api.get("/search", { ...params, limit: PAGE, offset });
      if (reqRef.current !== id) return; // filters changed mid-flight → drop
      setResults((prev) => [...(prev || []), ...res.results]);
      setTotal(res.total);
    } catch {
      /* keep current results on load-more failure */
    } finally {
      if (reqRef.current === id) setLoadingMore(false);
    }
  }

  const hasMore = !!results && results.length < total;

  // Auto-load the next page when the sentinel scrolls into view.
  const sentinel = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    const el = sentinel.current;
    if (!el || !hasMore) return;
    const obs = new IntersectionObserver((entries) => {
      if (entries[0]?.isIntersecting) loadMore();
    }, { rootMargin: "600px" });
    obs.observe(el);
    return () => obs.disconnect();
  }, [hasMore, results, loadingMore, loading, params]);

  const activeFilters = [genre, actor, platform, year, kind].filter(Boolean).length;

  function clearAll() {
    setQ(""); setGenre(""); setActor(""); setPlatform(""); setYear(""); setKind("");
  }

  return (
    <>
      <h1 className="large-title" style={{ marginBottom: 16 }}>{t("search.title")}</h1>

      <div className="card" style={{ marginBottom: 20 }}>
        <div className="row" style={{ gap: 10, marginBottom: 14 }}>
          <IconSearch width={20} height={20} className="muted" />
          <input value={q} onChange={(e) => setQ(e.target.value)} autoFocus
            placeholder={t("search.placeholder")} style={{ border: "none", minHeight: 32, padding: 0, background: "transparent" }} />
        </div>
        <hr className="divider" style={{ margin: "0 0 14px" }} />
        <div className="filters-grid">
          <div>
            <label>{t("search.type")}</label>
            <select value={kind} onChange={(e) => setKind(e.target.value)}>
              <option value="">{t("search.all")}</option>
              <option value="movie">{t("common.movies")}</option>
              <option value="series">{t("common.series")}</option>
            </select>
          </div>
          <div>
            <label>{t("search.platform")}</label>
            <select value={platform} onChange={(e) => setPlatform(e.target.value)}>
              <option value="">{t("search.any")}</option>
              {platformOptions.map((p) => <option key={p.key} value={p.key}>{p.label}</option>)}
            </select>
          </div>
          <div>
            <label>{t("search.genre")}</label>
            <input value={genre} onChange={(e) => setGenre(e.target.value)} placeholder={t("search.genrePlaceholder")} />
          </div>
          <div>
            <label>{t("search.actor")}</label>
            <input value={actor} onChange={(e) => setActor(e.target.value)} placeholder={t("search.actorPlaceholder")} />
          </div>
          <div>
            <label>{t("search.year")}</label>
            <input value={year} onChange={(e) => setYear(e.target.value.replace(/\D/g, ""))} placeholder="2025"
              inputMode="numeric" maxLength={4} />
          </div>
        </div>
        {activeFilters > 0 && (
          <div className="row" style={{ marginTop: 14 }}>
            <span className="caption">{activeFilters > 1 ? t("search.filtersActive", { count: activeFilters }) : t("search.filterActive", { count: activeFilters })}</span>
            <div className="spacer" />
            <button className="btn-ghost btn-sm" onClick={clearAll}>{t("search.clearFilters")}</button>
          </div>
        )}
      </div>

      {loading && !results ? <Loading /> :
        error ? <ErrorState error={error} /> :
        results === null ? (
          <Empty title={t("search.searchVault")} hint={t("search.searchVaultHint")} />
        ) : results.length === 0 ? (
          <Empty title={t("search.noMatches")} hint={t("search.noMatchesHint")} />
        ) : (
          <>
            <p className="muted" style={{ marginBottom: 14 }}>{total !== 1 ? t("search.titles", { count: total }) : t("search.titleOne", { count: total })}</p>
            <div className="poster-grid">
              {results.map((rt) => {
                const p0 = rt.platforms?.[0];
                const plat = p0 ? providerLabel(t, p0.key, p0.name) : "";
                return (
                  <Poster key={rt.id} to={`/title/${rt.id}`} poster={rt.poster} title={rt.title} kind={rt.kind}
                    enrichId={rt.id}
                    badge={rt.kind === "movie" ? t("common.film") : t("common.series")}
                    subtitle={`${plat}${rt.last_watched ? " · " + fmtDate(rt.last_watched) : ""}`} />
                );
              })}
            </div>
            {hasMore && (
              <div ref={sentinel} className="row" style={{ justifyContent: "center", marginTop: 20 }}>
                <button className="btn-ghost" onClick={loadMore} disabled={loadingMore}>
                  {loadingMore ? t("common.loading") : t("search.loadMore")}
                </button>
              </div>
            )}
          </>
        )}
    </>
  );
}
