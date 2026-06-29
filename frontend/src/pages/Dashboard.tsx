import { Link } from "react-router-dom";
import { useApp } from "../lib/app";
import { api } from "../lib/api";
import { useFetch } from "../lib/useFetch";
import { Spark } from "../components/charts";
import { Loading, ErrorState, Empty, Stat, Poster, Section } from "../components/ui";
import { fmtHours, fmtNum, monthKey, monthLabel } from "../lib/format";
import { IconChart, IconImport } from "../components/icons";

export function Dashboard() {
  const { scope, user } = useApp();
  const thisMonth = monthKey(new Date());

  const summary = useFetch<any>(() => api.get("/stats/summary", { profile: scope }), [scope]);
  const month = useFetch<any[]>(() => api.get("/stats/month", { profile: scope, month: thisMonth }), [scope, thisMonth]);

  if (summary.loading) return <Loading />;
  if (summary.error) return <ErrorState error={summary.error} retry={summary.reload} />;

  const s = summary.data;
  if (!s || s.empty || !s.totals || s.totals.events === 0) {
    return (
      <Empty
        title={`Welcome, ${user?.display_name?.split(" ")[0] || "there"} 👋`}
        hint="No watch history yet. Import a Netflix CSV or connect Plex/Jellyfin to start building your household's vault."
        action={<Link to="/imports" className="btn btn-primary"><IconImport width={18} height={18} /> Import history</Link>}
      />
    );
  }

  const spark = (s.recent || []).map((r: any) => ({
    label: r.date, value: r.count,
  }));

  const scopeName = scope === "all" ? "the household" : "this profile";

  return (
    <>
      <div className="section-head">
        <div className="col" style={{ gap: 2 }}>
          <h1 className="large-title">Dashboard</h1>
          <span className="muted">An overview for {scopeName}</span>
        </div>
      </div>

      <div className="stat-grid" style={{ marginBottom: 24 }}>
        <Stat value={fmtHours(s.totals.hours)} label="Total watch time" />
        <Stat value={fmtNum(s.totals.titles)} label="Unique titles" />
        <Stat value={fmtNum(s.totals.movies)} label="Movies" />
        <Stat value={fmtNum(s.totals.episodes)} label="Episodes" />
      </div>

      <div className="card" style={{ marginBottom: 24 }}>
        <div className="row">
          <div className="col" style={{ gap: 2 }}>
            <span className="headline">Last 30 days</span>
            <span className="caption">{fmtNum(s.this_month.events)} this month · {fmtHours(s.this_month.hours)}</span>
          </div>
          <div className="spacer" />
          <Link to="/overviews" className="btn-ghost btn-sm"><IconChart width={16} height={16} /> Trends</Link>
        </div>
        {spark.length > 1 ? <Spark data={spark} height={70} /> :
          <p className="caption" style={{ marginTop: 12 }}>Not enough data yet for a trend.</p>}
      </div>

      {s.providers?.length > 0 && (
        <div className="card" style={{ marginBottom: 24 }}>
          <span className="headline">By platform</span>
          <div className="col" style={{ marginTop: 12, gap: 12 }}>
            {s.providers.slice(0, 6).map((p: any) => {
              const maxH = Math.max(...s.providers.map((x: any) => x.hours), 1);
              return (
                <div key={p.key} className="row" style={{ gap: 12 }}>
                  <span style={{ width: 92, fontWeight: 600, fontSize: "0.9rem" }}>{p.name}</span>
                  <div className="bar-track" style={{ flex: 1 }}>
                    <div className="bar-fill" style={{ width: `${(p.hours / maxH) * 100}%`, background: p.color || "var(--accent)" }} />
                  </div>
                  <span className="caption" style={{ width: 60, textAlign: "right" }}>{fmtHours(p.hours)}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      <Section title={`Watched in ${monthLabel(thisMonth)}`}
        right={<Link to="/overviews" className="btn-ghost btn-sm">All months</Link>}>
        {month.loading ? <Loading /> :
          month.data && month.data.length > 0 ? (
            <div className="poster-grid">
              {month.data.slice(0, 12).map((t) => (
                <Poster key={t.id} to={`/title/${t.id}`} poster={t.poster} title={t.title} kind={t.kind}
                  subtitle={t.kind === "movie" ? `${t.year || ""}` : `${t.episodes} ep · ${fmtHours(t.hours)}`}
                  badge={t.kind === "movie" ? "Film" : "Series"} />
              ))}
            </div>
          ) : <p className="muted">Nothing watched yet this month.</p>}
      </Section>
    </>
  );
}
