import { useEffect, useMemo, useState } from "react";
import { useApp } from "../lib/app";
import { useT } from "../lib/i18n";
import { api } from "../lib/api";
import { Loading, Empty, Poster, ErrorState } from "../components/ui";
import { IconSearch } from "../components/icons";
import { fmtHours, fmtDate } from "../lib/format";

interface Provider { key: string; name: string; }

export function Search() {
  const { scope } = useApp();
  const { t, lang } = useT();
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

  const params = useMemo(() => ({ profile: scope, q, genre, actor, platform, year, kind, lang }),
    [scope, q, genre, actor, platform, year, kind, lang]);

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
              {providers.map((p) => <option key={p.key} value={p.key}>{p.name}</option>)}
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
              {results.map((rt) => (
                <Poster key={rt.id} to={`/title/${rt.id}`} poster={rt.poster} title={rt.title} kind={rt.kind}
                  enrichId={rt.id}
                  badge={rt.kind === "movie" ? t("common.film") : t("common.series")}
                  subtitle={`${rt.platforms?.[0] || ""}${rt.last_watched ? " · " + fmtDate(rt.last_watched) : ""}`} />
              ))}
            </div>
          </>
        )}
    </>
  );
}
