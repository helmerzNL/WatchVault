import { useMemo, useState } from "react";
import { useApp } from "../lib/app";
import { api } from "../lib/api";
import { useFetch } from "../lib/useFetch";
import { TrendArea, StackedBars, HBars } from "../components/charts";
import { Heatmap } from "../components/Heatmap";
import { Loading, ErrorState, Poster, Section } from "../components/ui";
import { fmtHours, fmtMonth, monthKey, monthLabel } from "../lib/format";

type Gran = "day" | "week" | "month";

function Seg<T extends string>({ value, onChange, options }: {
  value: T; onChange: (v: T) => void; options: { value: T; label: string }[];
}) {
  return (
    <div className="seg">
      {options.map((o) => (
        <button key={o.value} className={value === o.value ? "active" : ""} onClick={() => onChange(o.value)}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

function HoursTrend({ scope }: { scope: string }) {
  const [gran, setGran] = useState<Gran>("month");
  const { data, loading, error, reload } = useFetch<any[]>(
    () => api.get("/stats/trend", { profile: scope, granularity: gran }), [scope, gran]);

  const series = useMemo(() => (data || []).map((r) => ({
    label: gran === "month" ? fmtMonth(r.period) : r.period.slice(5),
    value: r.hours,
  })), [data, gran]);

  return (
    <Section title="Watch time over time"
      right={<Seg value={gran} onChange={setGran} options={[
        { value: "day", label: "Day" }, { value: "week", label: "Week" }, { value: "month", label: "Month" }]} />}>
      <div className="card">
        {loading ? <Loading /> : error ? <ErrorState error={error} retry={reload} /> :
          series.length ? <TrendArea data={series} /> : <p className="muted">No data in this range.</p>}
      </div>
    </Section>
  );
}

function PlatformBreakdown({ scope }: { scope: string }) {
  const [period, setPeriod] = useState<"month" | "year">("month");
  const { data, loading, error, reload } = useFetch<any[]>(
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
      series: Array.from(platforms.entries()).map(([key, v]) => ({ key, name: v.name, color: v.color || "var(--accent)" })),
    };
  }, [data, period]);

  return (
    <Section title="Per platform"
      right={<Seg value={period} onChange={setPeriod} options={[
        { value: "month", label: "Monthly" }, { value: "year", label: "Yearly" }]} />}>
      <div className="card">
        {loading ? <Loading /> : error ? <ErrorState error={error} retry={reload} /> :
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
          ) : <p className="muted">No platform data yet.</p>}
      </div>
    </Section>
  );
}

function DailyHeatmap({ scope }: { scope: string }) {
  const years = useMemo(() => {
    const y = new Date().getFullYear();
    return [y, y - 1, y - 2];
  }, []);
  const [year, setYear] = useState(years[0]);
  const { data, loading, error, reload } = useFetch<any[]>(
    () => api.get("/stats/heatmap", { profile: scope, year }), [scope, year]);

  return (
    <Section title="Daily activity"
      right={<Seg value={String(year)} onChange={(v) => setYear(Number(v))}
        options={years.map((y) => ({ value: String(y), label: String(y) }))} />}>
      <div className="card" style={{ overflowX: "auto" }}>
        {loading ? <Loading /> : error ? <ErrorState error={error} retry={reload} /> :
          <Heatmap days={data || []} year={year} />}
      </div>
    </Section>
  );
}

function MonthlyTitles({ scope }: { scope: string }) {
  const [month, setMonth] = useState(monthKey(new Date()));
  const { data, loading, error, reload } = useFetch<any[]>(
    () => api.get("/stats/month", { profile: scope, month }), [scope, month]);

  return (
    <Section title="Watched per month"
      right={<input type="month" value={month} onChange={(e) => setMonth(e.target.value)}
        style={{ width: "auto", minHeight: 36, padding: "6px 10px" }} />}>
      {loading ? <Loading /> : error ? <ErrorState error={error} retry={reload} /> :
        data && data.length ? (
          <div className="poster-grid">
            {data.map((t) => (
              <Poster key={t.id} to={`/title/${t.id}`} poster={t.poster} title={t.title} kind={t.kind}
                subtitle={t.kind === "movie" ? `${t.year || ""}` : `${t.episodes} ep · ${fmtHours(t.hours)}`}
                badge={t.kind === "movie" ? "Film" : "Series"} />
            ))}
          </div>
        ) : <p className="muted">Nothing watched in {monthLabel(month)}.</p>}
    </Section>
  );
}

function GenreActor({ scope }: { scope: string }) {
  const genre = useFetch<any[]>(() => api.get("/stats/by-genre", { profile: scope }), [scope]);
  const actor = useFetch<any[]>(() => api.get("/stats/by-actor", { profile: scope, limit: 12 }), [scope]);

  const genreData = (genre.data || []).slice(0, 10).map((g) => ({ label: g.genre, value: g.hours }));

  return (
    <div className="grid-2">
      <Section title="Time per genre">
        <div className="card">
          {genre.loading ? <Loading /> :
            genreData.length ? <HBars data={genreData} height={Math.max(220, genreData.length * 30)} /> :
              <p className="muted">No genre data yet — enrich titles with TMDB in Settings.</p>}
        </div>
      </Section>
      <Section title="Time per actor">
        <div className="card">
          {actor.loading ? <Loading /> :
            actor.data && actor.data.length ? (
              <div className="col" style={{ gap: 10 }}>
                {actor.data.map((a, i) => {
                  const maxH = Math.max(...actor.data!.map((x) => x.hours), 1);
                  return (
                    <div key={a.id} className="row" style={{ gap: 12 }}>
                      <span className="avatar" style={{ width: 34, height: 34, fontSize: 12 }}>
                        {a.profile ? <img src={a.profile} alt="" /> : i + 1}
                      </span>
                      <div className="col" style={{ flex: 1, gap: 4 }}>
                        <div className="row"><span style={{ fontWeight: 600, fontSize: "0.9rem", flex: 1 }}>{a.name}</span>
                          <span className="caption">{fmtHours(a.hours)}</span></div>
                        <div className="bar-track"><div className="bar-fill" style={{ width: `${(a.hours / maxH) * 100}%` }} /></div>
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : <p className="muted">No cast data yet — enrich titles with TMDB in Settings.</p>}
        </div>
      </Section>
    </div>
  );
}

export function Overviews() {
  const { scope } = useApp();
  return (
    <>
      <h1 className="large-title" style={{ marginBottom: 8 }}>Overviews</h1>
      <HoursTrend scope={scope} />
      <DailyHeatmap scope={scope} />
      <PlatformBreakdown scope={scope} />
      <MonthlyTitles scope={scope} />
      <GenreActor scope={scope} />
    </>
  );
}
