import { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useApp } from "../lib/app";
import { useT, providerLabelShort, useGenre, mediaBadge } from "../lib/i18n";
import { api } from "../lib/api";
import { Loading, Empty, Poster, ErrorState } from "../components/ui";
import { IconSearch } from "../components/icons";
import { fmtHours, fmtDate } from "../lib/format";
import { AddCinemaFilmButton } from "../components/AddCinemaFilm";

interface Provider { key: string; name: string; }

const PAGE = 60;

export function Search() {
  const { scope } = useApp();
  const { t, lang } = useT();
  const tGenre = useGenre();
  const [searchParams, setSearchParams] = useSearchParams();
  const [q, setQ] = useState(() => searchParams.get("q") || "");
  const [genre, setGenre] = useState(() => searchParams.get("genre") || "");
  const [actor, setActor] = useState(() => searchParams.get("actor") || "");
  const [platform, setPlatform] = useState(() => searchParams.get("platform") || "");
  const [year, setYear] = useState(() => searchParams.get("year") || "");
  const [kind, setKind] = useState(() => searchParams.get("kind") || "");
  const [tag, setTag] = useState(() => searchParams.get("tag") || "");
  const [providers, setProviders] = useState<Provider[]>([]);
  const [tagOptions, setTagOptions] = useState<{ id: string; name: string }[]>([]);
  const [genreOptions, setGenreOptions] = useState<string[]>([]);
  const [yearOptions, setYearOptions] = useState<number[]>([]);

  const [results, setResults] = useState<any[] | null>(null);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<unknown>(null);
  // Bumped on every filter-driven (page-0) reload so an in-flight loadMore from a
  // previous filter set can detect it is stale and drop its appended results.
  const reqRef = useRef(0);

  useEffect(() => { api.get("/providers").then(setProviders).catch(() => {}); }, []);
  useEffect(() => { api.get("/tags").then(setTagOptions).catch(() => {}); }, []);

  // Available genres / release years for the current scope, driving the filter
  // dropdowns so users pick from what they've actually watched.
  useEffect(() => {
    api.get("/search/facets", { profile: scope })
      .then((f) => { setGenreOptions(f.genres || []); setYearOptions(f.years || []); })
      .catch(() => {});
  }, [scope]);

  // Keep the currently selected value available as an option even if it isn't in
  // the fetched facets (e.g. a genre passed in via the URL from another page).
  const genreSelectOptions = useMemo(() => {
    const set = new Set(genreOptions);
    if (genre) set.add(genre);
    return Array.from(set).sort((a, b) => tGenre(a).localeCompare(tGenre(b)));
  }, [genreOptions, genre, tGenre]);

  const yearSelectOptions = useMemo(() => {
    const set = new Set(yearOptions.map(String));
    if (year) set.add(year);
    return Array.from(set).map(Number).sort((a, b) => b - a);
  }, [yearOptions, year]);

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
    if (tag) next.tag = tag;
    setSearchParams(next, { replace: true });
  }, [q, genre, actor, platform, year, kind, tag, setSearchParams]);

  const params = useMemo(() => ({ profile: scope, q, genre, actor, platform, year, kind, tag, lang }),
    [scope, q, genre, actor, platform, year, kind, tag, lang]);

  // Plex + Jellyfin are presented as one "Digital Library" option; selecting it
  // filters on either (the backend expands the `digital_library` key).
  const platformOptions = useMemo(() => {
    const out: { key: string; label: string }[] = [];
    let digital = false;
    for (const p of providers) {
      if (p.key === "plex" || p.key === "jellyfin") {
        if (digital) continue;
        digital = true;
        out.push({ key: "digital_library", label: providerLabelShort(t, "digital_library", p.name) });
      } else {
        out.push({ key: p.key, label: providerLabelShort(t, p.key, p.name) });
      }
    }
    return out;
  }, [providers, t]);

  // debounced page-0 (re)load whenever filters change
  useEffect(() => {
    const hasFilter = q || genre || actor || platform || year || kind || tag;
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

  const activeFilters = [genre, actor, platform, year, kind, tag].filter(Boolean).length;

  function clearAll() {
    setQ(""); setGenre(""); setActor(""); setPlatform(""); setYear(""); setKind(""); setTag("");
  }

  return (
    <>
      <div className="row" style={{ marginBottom: 16, gap: 12 }}>
        <h1 className="large-title" style={{ margin: 0 }}>{t("search.title")}</h1>
        <div className="spacer" style={{ flex: 1 }} />
        <AddCinemaFilmButton />
      </div>

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
              <option value="unknown">{t("common.unknown")}</option>
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
            <select value={genre} onChange={(e) => setGenre(e.target.value)}>
              <option value="">{t("search.any")}</option>
              {genreSelectOptions.map((g) => <option key={g} value={g}>{tGenre(g)}</option>)}
            </select>
          </div>
          <div>
            <label>{t("search.actor")}</label>
            <input value={actor} onChange={(e) => setActor(e.target.value)} placeholder={t("search.actorPlaceholder")} />
          </div>
          <div>
            <label>{t("search.year")}</label>
            <select value={year} onChange={(e) => setYear(e.target.value)}>
              <option value="">{t("search.any")}</option>
              {yearSelectOptions.map((y) => <option key={y} value={String(y)}>{y}</option>)}
            </select>
          </div>
          {tagOptions.length > 0 && (
            <div>
              <label>{t("tags.label")}</label>
              <select value={tag} onChange={(e) => setTag(e.target.value)}>
                <option value="">{t("search.any")}</option>
                {tagOptions.map((tg) => <option key={tg.id} value={tg.id}>{tg.name}</option>)}
              </select>
            </div>
          )}
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
                const plat = p0 ? providerLabelShort(t, p0.key, p0.name) : "";
                return (
                  <Poster key={rt.id} to={`/title/${rt.id}`} poster={rt.poster} title={rt.title} kind={rt.kind}
                    enrichId={rt.id}
                    badge={mediaBadge(t, rt)}
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
