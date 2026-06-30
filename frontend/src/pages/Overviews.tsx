import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useApp } from "../lib/app";
import { useT, useGenre, providerLabel } from "../lib/i18n";
import { api } from "../lib/api";
import { useFetch } from "../lib/useFetch";
import { TrendArea, StackedBars } from "../components/charts";
import { Heatmap } from "../components/Heatmap";
import { Loading, ErrorState, Poster, Section, Seg, MonthNav, RangeSeg, type Range } from "../components/ui";
import { fmtDate, fmtHours, fmtMonth, fmtDayMonth, monthKey, monthLabel } from "../lib/format";

type Gran = "day" | "week" | "month";

function HoursTrend({ scope }: { scope: string }) {
  const { t } = useT();
  const [gran, setGran] = useState<Gran>("month");
  const { data, error, reload } = useFetch<any[]>(
    () => api.get("/stats/trend", { profile: scope, granularity: gran }), [scope, gran]);

  const series = useMemo(() => (data || []).map((r) => ({
    label: gran === "month" ? fmtMonth(r.period) : fmtDayMonth(r.period),
    value: r.hours,
  })), [data, gran]);

  return (
    <Section title={t("overviews.watchTimeOverTime")}>
      <div className="card">
        <div className="row" style={{ marginBottom: 12 }}>
          <div className="spacer" style={{ flex: 1 }} />
          <Seg value={gran} onChange={setGran} options={[
            { value: "day", label: t("overviews.day") }, { value: "week", label: t("overviews.week") }, { value: "month", label: t("overviews.month") }]} />
        </div>
        {error ? <ErrorState error={error} retry={reload} /> :
          data == null ? <Loading /> :
          series.length ? <TrendArea data={series} /> : <p className="muted">{t("overviews.noDataRange")}</p>}
      </div>
    </Section>
  );
}

function PlatformBreakdown({ scope }: { scope: string }) {
  const { t } = useT();
  const [period, setPeriod] = useState<"month" | "year">("month");
  const { data, error, reload } = useFetch<any[]>(
    () => api.get("/stats/by-platform", { profile: scope, period }), [scope, period]);

  const { rows, series } = useMemo(() => {
    const byPeriod = new Map<string, any>();
    const platforms = new Map<string, { name: string; color: string }>();
    for (const r of data || []) {
      const label = period === "year" ? r.period.slice(0, 4) : fmtMonth(r.period);
      if (!byPeriod.has(label)) byPeriod.set(label, { label });
      byPeriod.get(label)[r.key] = (byPeriod.get(label)[r.key] || 0) + r.events;
      if (!platforms.has(r.key)) platforms.set(r.key, { name: r.name, color: r.color });
    }
    return {
      rows: Array.from(byPeriod.values()),
      series: Array.from(platforms.entries()).map(([key, v]) => ({ key, name: providerLabel(t, key, v.name), color: v.color || "var(--accent)" })),
    };
  }, [data, period, t]);

  return (
    <Section title={t("overviews.perPlatform")}>
      <div className="card">
        <div className="row" style={{ marginBottom: 12 }}>
          <div className="spacer" style={{ flex: 1 }} />
          <Seg value={period} onChange={setPeriod} options={[
            { value: "month", label: t("overviews.monthly") }, { value: "year", label: t("overviews.yearly") }]} />
        </div>
        {error ? <ErrorState error={error} retry={reload} /> :
          data == null ? <Loading /> :
          rows.length ? (
            <>
              <StackedBars data={rows} series={series} />
              <div className="chips" style={{ marginTop: 12 }}>
                {series.map((s) => (
                  <span key={s.key} className="caption row" style={{ gap: 6 }}>
                    <span style={{ width: 10, height: 10, borderRadius: 3, background: s.color, display: "inline-block" }} />
                    {s.name}
                  </span>
                ))}
              </div>
            </>
          ) : <p className="muted">{t("overviews.noPlatformData")}</p>}
      </div>
    </Section>
  );
}

function DailyHeatmap({ scope }: { scope: string }) {
  const { t } = useT();
  const cur = new Date().getFullYear();
  // Offer every year that actually has data (newest first), not just a fixed
  // 2-year window, so older history stays reachable.
  const { data: yearsData } = useFetch<number[]>(
    () => api.get("/stats/years", { profile: scope }), [scope]);
  const years = useMemo(() => {
    const set = new Set<number>([cur, cur - 1, cur - 2, ...(yearsData || [])]);
    return Array.from(set).sort((a, b) => b - a);
  }, [yearsData, cur]);
  const [year, setYear] = useState(cur);
  const [selected, setSelected] = useState<string | null>(null);
  const { data, loading, error, reload } = useFetch<any[]>(
    () => api.get("/stats/heatmap", { profile: scope, year }), [scope, year]);

  // Reset the open day when the profile or year changes.
  useEffect(() => { setSelected(null); }, [scope, year]);

  const dayMedia = useFetch<any[]>(
    () => (selected ? api.get("/stats/day", { profile: scope, date: selected })
                    : Promise.resolve([])), [scope, selected]);

  return (
    <Section title={t("overviews.dailyActivity")}
      right={years.length > 3
        ? <select value={String(year)} onChange={(e) => setYear(Number(e.target.value))}
            aria-label={t("overviews.dailyActivity")} style={{ width: "auto", minHeight: 0 }}>
            {years.map((y) => <option key={y} value={String(y)}>{y}</option>)}
          </select>
        : <Seg value={String(year)} onChange={(v) => setYear(Number(v))}
            options={years.map((y) => ({ value: String(y), label: String(y) }))} />}>
      <div className="card" style={{ overflowX: "auto" }}>
        {loading ? <Loading /> : error ? <ErrorState error={error} retry={reload} /> :
          <Heatmap days={data || []} year={year} selected={selected} onSelect={setSelected} />}
      </div>
      {selected && (
        <div className="card" style={{ marginTop: 12 }}>
          <div className="row" style={{ alignItems: "center", marginBottom: 12 }}>
            <h3 style={{ margin: 0, flex: 1, fontSize: "1.02rem" }}>{fmtDate(selected)}</h3>
            <button className="btn-ghost" onClick={() => setSelected(null)} aria-label={t("common.close")}>✕</button>
          </div>
          {dayMedia.loading ? <Loading /> :
            dayMedia.data && dayMedia.data.length ? (
              <div className="poster-grid">
                {dayMedia.data.map((m) => (
                  <Poster key={m.id} to={`/title/${m.id}`} poster={m.poster} title={m.title} kind={m.kind}
                    enrichId={m.id}
                    subtitle={m.kind === "movie" ? `${m.year || ""}` : `${m.episodes} ep · ${fmtHours(m.hours)}`}
                    badge={m.kind === "movie" ? t("common.film") : t("common.series")} />
                ))}
              </div>
            ) : <p className="muted">{t("overviews.nothingOnDay")}</p>}
        </div>
      )}
    </Section>
  );
}

function MonthlyTitles({ scope }: { scope: string }) {
  const { t } = useT();
  const [month, setMonth] = useState(monthKey(new Date()));
  const { data, loading, error, reload } = useFetch<any[]>(
    () => api.get("/stats/month", { profile: scope, month }), [scope, month]);

  return (
    <Section title={t("overviews.watchedPerMonth")}
      right={<MonthNav value={month} onChange={setMonth} />}>
      {loading ? <Loading /> : error ? <ErrorState error={error} retry={reload} /> :
        data && data.length ? (
          <div className="poster-grid">
            {data.map((t2) => (
              <Poster key={t2.id} to={`/title/${t2.id}`} poster={t2.poster} title={t2.title} kind={t2.kind}
                enrichId={t2.id}
                subtitle={t2.kind === "movie" ? `${t2.year || ""}` : `${t2.episodes} ep · ${fmtHours(t2.hours)}`}
                badge={t2.kind === "movie" ? t("common.film") : t("common.series")} />
            ))}
          </div>
        ) : <p className="muted">{t("overviews.nothingIn", { month: monthLabel(month) })}</p>}
    </Section>
  );
}

function GenreActor({ scope }: { scope: string }) {
  const { t } = useT();
  const tGenre = useGenre();
  const [genreRange, setGenreRange] = useState<Range>("all");
  const [actorRange, setActorRange] = useState<Range>("all");
  const genre = useFetch<any[]>(() => api.get("/stats/by-genre", { profile: scope, range: genreRange }), [scope, genreRange]);
  const actor = useFetch<any[]>(() => api.get("/stats/by-actor", { profile: scope, limit: 12, range: actorRange }), [scope, actorRange]);

  const genreData = (genre.data || []).slice(0, 10);
  const genreMax = Math.max(...genreData.map((g) => g.hours), 1);

  return (
    <div className="grid-2">
      <div>
        <Section title={t("overviews.timePerGenre")}>
          <div className="card">
            <div className="row" style={{ marginBottom: 12 }}>
              <div className="spacer" style={{ flex: 1 }} />
              <RangeSeg value={genreRange} onChange={setGenreRange} />
            </div>
            {genre.loading ? <Loading /> :
              genreData.length ? (
                <div className="col" style={{ gap: 10 }}>
                  {genreData.map((g) => (
                    <Link key={g.genre_id} to={`/genre/${g.genre_id}`} className="row"
                      style={{ gap: 12, color: "inherit", textDecoration: "none" }}>
                      <div className="col" style={{ flex: 1, gap: 4 }}>
                        <div className="row"><span style={{ fontWeight: 600, fontSize: "0.9rem", flex: 1 }}>{tGenre(g.genre)}</span>
                          <span className="caption">{fmtHours(g.hours)}</span></div>
                        <div className="bar-track"><div className="bar-fill" style={{ width: `${(g.hours / genreMax) * 100}%` }} /></div>
                      </div>
                    </Link>
                  ))}
                </div>
              ) : <p className="muted">{t("overviews.noGenreData")}</p>}
          </div>
        </Section>
      </div>
      <div>
        <Section title={t("overviews.timePerActor")}>
          <div className="card">
            <div className="row" style={{ marginBottom: 12 }}>
              <div className="spacer" style={{ flex: 1 }} />
              <RangeSeg value={actorRange} onChange={setActorRange} />
            </div>
            {actor.loading ? <Loading /> :
              actor.data && actor.data.length ? (
                <div className="col" style={{ gap: 10 }}>
                  {actor.data.map((a, i) => {
                    const maxH = Math.max(...actor.data!.map((x) => x.hours), 1);
                    return (
                      <Link key={a.id} to={`/person/${a.id}`} className="row" style={{ gap: 12, color: "inherit", textDecoration: "none" }}>
                        <span className="avatar" style={{ width: 34, height: 34, fontSize: 12 }}>
                          {a.profile ? <img src={a.profile} alt="" /> : i + 1}
                        </span>
                        <div className="col" style={{ flex: 1, gap: 4 }}>
                          <div className="row"><span style={{ fontWeight: 600, fontSize: "0.9rem", flex: 1 }}>{a.name}</span>
                            <span className="caption">{fmtHours(a.hours)}</span></div>
                          <div className="bar-track"><div className="bar-fill" style={{ width: `${(a.hours / maxH) * 100}%` }} /></div>
                        </div>
                      </Link>
                    );
                  })}
                </div>
              ) : <p className="muted">{t("overviews.noCastData")}</p>}
          </div>
        </Section>
      </div>
    </div>
  );
}

export function Overviews() {
  const { scope } = useApp();
  const { t } = useT();
  return (
    <>
      <h1 className="large-title" style={{ marginBottom: 8 }}>{t("overviews.title")}</h1>
      <HoursTrend scope={scope} />
      <DailyHeatmap scope={scope} />
      <PlatformBreakdown scope={scope} />
      <MonthlyTitles scope={scope} />
      <GenreActor scope={scope} />
    </>
  );
}
