import { Link } from "react-router-dom";
import { useApp } from "../lib/app";
import { useT } from "../lib/i18n";
import { api } from "../lib/api";
import { useFetch } from "../lib/useFetch";
import { Spark } from "../components/charts";
import { Loading, ErrorState, Empty, Stat, Poster, Section } from "../components/ui";
import { fmtHours, fmtNum, monthKey, monthLabel } from "../lib/format";
import { IconChart, IconImport } from "../components/icons";

export function Dashboard() {
  const { scope, user } = useApp();
  const { t } = useT();
  const thisMonth = monthKey(new Date());

  const summary = useFetch<any>(() => api.get("/stats/summary", { profile: scope }), [scope]);
  const month = useFetch<any[]>(() => api.get("/stats/month", { profile: scope, month: thisMonth }), [scope, thisMonth]);

  if (summary.loading) return <Loading />;
  if (summary.error) return <ErrorState error={summary.error} retry={summary.reload} />;

  const s = summary.data;
  if (!s || s.empty || !s.totals || s.totals.events === 0) {
    return (
      <Empty
        title={t("dashboard.welcome", { name: user?.display_name?.split(" ")[0] || "there" })}
        hint={t("dashboard.noHistory")}
        action={<Link to="/imports" className="btn btn-primary"><IconImport width={18} height={18} /> {t("dashboard.importHistory")}</Link>}
      />
    );
  }

  const spark = (s.recent || []).map((r: any) => ({
    label: r.date, value: r.count,
  }));

  const scopeName = scope === "all" ? t("dashboard.theHousehold") : t("dashboard.thisProfile");

  return (
    <>
      <div className="section-head">
        <div className="col" style={{ gap: 2 }}>
          <h1 className="large-title">{t("nav.dashboard")}</h1>
          <span className="muted">{t("dashboard.overviewFor", { scope: scopeName })}</span>
        </div>
      </div>

      <div className="stat-grid" style={{ marginBottom: 24 }}>
        <Stat value={fmtHours(s.totals.hours)} label={t("dashboard.totalWatchTime")} />
        <Stat value={fmtNum(s.totals.titles)} label={t("dashboard.uniqueTitles")} />
        <Stat value={fmtNum(s.totals.movies)} label={t("common.movies")} />
        <Stat value={fmtNum(s.totals.episodes)} label={t("common.episodes")} />
      </div>

      <div className="card" style={{ marginBottom: 24 }}>
        <div className="row">
          <div className="col" style={{ gap: 2 }}>
            <span className="headline">{t("dashboard.last30")}</span>
            <span className="caption">{t("dashboard.thisMonthSummary", { events: fmtNum(s.this_month.events), hours: fmtHours(s.this_month.hours) })}</span>
          </div>
          <div className="spacer" />
          <Link to="/overviews" className="btn-ghost btn-sm"><IconChart width={16} height={16} /> {t("dashboard.trends")}</Link>
        </div>
        {spark.length > 1 ? <Spark data={spark} height={70} /> :
          <p className="caption" style={{ marginTop: 12 }}>{t("dashboard.notEnoughTrend")}</p>}
      </div>

      {s.providers?.length > 0 && (
        <div className="card" style={{ marginBottom: 24 }}>
          <span className="headline">{t("dashboard.byPlatform")}</span>
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

      <Section title={t("dashboard.watchedIn", { month: monthLabel(thisMonth) })}
        right={<Link to="/overviews" className="btn-ghost btn-sm">{t("dashboard.allMonths")}</Link>}>
        {month.loading ? <Loading /> :
          month.data && month.data.length > 0 ? (
            <div className="poster-grid">
              {month.data.slice(0, 12).map((t2) => (
                <Poster key={t2.id} to={`/title/${t2.id}`} poster={t2.poster} title={t2.title} kind={t2.kind}
                  enrichId={t2.id}
                  subtitle={t2.kind === "movie" ? `${t2.year || ""}` : `${t2.episodes} ep · ${fmtHours(t2.hours)}`}
                  badge={t2.kind === "movie" ? t("common.film") : t("common.series")} />
              ))}
            </div>
          ) : <p className="muted">{t("dashboard.nothingThisMonth")}</p>}
      </Section>
    </>
  );
}
