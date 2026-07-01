import { useState, useEffect, Fragment, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { useApp } from "../lib/app";
import { useT, providerLabel } from "../lib/i18n";
import { api } from "../lib/api";
import { useFetch } from "../lib/useFetch";
import { Spark } from "../components/charts";
import { Loading, ErrorState, Empty, Stat, Poster, Section, MonthNav, RangeSeg, Seg, type Range } from "../components/ui";
import { fmtHours, fmtNum, fmtMonth, fmtDayMonth, monthKey, monthLabel } from "../lib/format";
import { IconChart, IconImport, IconEye, IconEyeOff, IconChevron } from "../components/icons";
import { AddCinemaFilmButton } from "../components/AddCinemaFilm";

type RecentRange = "week" | "month" | "year";

// Dashboard blocks are a registry so the layout can be reordered / hidden per
// user (persisted in prefs.dashboard_layout, synced via /preferences). Blocks
// marked `expert` only appear when Expert mode is on. Unknown/new ids in a saved
// layout are ignored and new blocks are appended, so old layouts stay valid.
type BlockId = "nowPlaying" | "unfinished" | "stats" | "trend" | "platforms" | "monthly";
const DEFAULT_ORDER: BlockId[] = ["nowPlaying", "unfinished", "stats", "trend", "platforms", "monthly"];

export function Dashboard() {
  const { scope, user, prefs, savePrefs } = useApp();
  const { t } = useT();
  const [range, setRange] = useState<Range>("all");
  const [recentRange, setRecentRange] = useState<RecentRange>("month");
  const [editing, setEditing] = useState(false);

  const summary = useFetch<any>(() => api.get("/stats/summary", { profile: scope }), [scope]);
  const providers = useFetch<any[]>(() => api.get("/stats/providers", { profile: scope, range }), [scope, range]);
  const recent = useFetch<any[]>(() => api.get("/stats/recent", { profile: scope, range: recentRange }), [scope, recentRange]);

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

  const spark = (recent.data ?? s.recent ?? []).map((r: any) => ({
    label: recentRange === "year" ? fmtMonth(r.date) : fmtDayMonth(r.date), value: r.count,
  }));
  const recentTitle = recentRange === "week" ? "dashboard.last7"
    : recentRange === "year" ? "dashboard.last12m" : "dashboard.last30";

  const scopeName = scope === "all" ? t("dashboard.theHousehold") : t("dashboard.thisProfile");

  const blocks: Record<BlockId, { labelKey: string; expert?: boolean; node: ReactNode }> = {
    nowPlaying: { labelKey: "dashboard.blockNowPlaying", expert: true, node: <NowPlaying scope={scope} /> },
    unfinished: { labelKey: "dashboard.blockUnfinished", expert: true, node: <UnfinishedTitles scope={scope} /> },
    stats: {
      labelKey: "dashboard.blockStats",
      node: (
        <div className="stat-grid" style={{ marginBottom: 24 }}>
          <Stat value={fmtHours(s.totals.hours)} label={t("dashboard.totalWatchTime")} />
          <Stat value={fmtNum(s.totals.titles)} label={t("dashboard.uniqueTitles")} />
          <Stat value={fmtNum(s.totals.movies)} label={t("common.movies")} />
          <Stat value={fmtNum(s.totals.episodes)} label={t("common.episodes")} />
          {prefs.expert && <Stat value={fmtHours((s.totals.remaining_minutes || 0) / 60)} label={t("dashboard.stillToWatch")} />}
          {prefs.expert && <Stat value={fmtNum(s.totals.remaining_items || 0)} label={t("dashboard.itemsUnfinished")} />}
        </div>
      ),
    },
    trend: {
      labelKey: "dashboard.blockTrend",
      node: (
        <div className="card" style={{ marginBottom: 24 }}>
          <div className="row">
            <div className="col" style={{ gap: 2 }}>
              <span className="headline">{t(recentTitle)}</span>
              <span className="caption">{t("dashboard.thisMonthSummary", { events: fmtNum(s.this_month.events), hours: fmtHours(s.this_month.hours) })}</span>
            </div>
            <div className="spacer" style={{ flex: 1 }} />
            <Seg<RecentRange> value={recentRange} onChange={setRecentRange} options={[
              { value: "week", label: t("overviews.week") },
              { value: "month", label: t("overviews.month") },
              { value: "year", label: t("overviews.year") },
            ]} />
            <Link to="/overviews" className="btn-ghost btn-sm" style={{ marginLeft: 8 }}><IconChart width={16} height={16} /> {t("dashboard.trends")}</Link>
          </div>
          {spark.length > 1 ? <Spark data={spark} height={70} /> :
            <p className="caption" style={{ marginTop: 12 }}>{t("dashboard.notEnoughTrend")}</p>}
        </div>
      ),
    },
    platforms: {
      labelKey: "dashboard.blockPlatforms",
      node: (
        <div className="card" style={{ marginBottom: 24 }}>
          <div className="row" style={{ marginBottom: 4 }}>
            <span className="headline">{t("dashboard.byPlatform")}</span>
            <div className="spacer" style={{ flex: 1 }} />
            <RangeSeg value={range} onChange={setRange} />
          </div>
          {providers.loading ? <div style={{ marginTop: 12 }}><Loading /></div> :
            (providers.data?.length ?? 0) > 0 ? (
              <div className="col" style={{ marginTop: 12, gap: 12 }}>
                {(() => {
                  const maxH = Math.max(...providers.data!.map((x: any) => x.hours), 1);
                  return providers.data!.map((p: any) => (
                    <div key={p.key} className="row" style={{ gap: 12 }}>
                      <span style={{ width: 92, fontWeight: 600, fontSize: "0.9rem" }}>{providerLabel(t, p.key, p.name)}</span>
                      <div className="bar-track" style={{ flex: 1 }}>
                        <div className="bar-fill" style={{ width: `${(p.hours / maxH) * 100}%`, background: p.color || "var(--accent)" }} />
                      </div>
                      <span className="caption" style={{ width: 60, textAlign: "right" }}>{fmtHours(p.hours)}</span>
                    </div>
                  ));
                })()}
              </div>
            ) : <p className="muted" style={{ marginTop: 12 }}>{t("dashboard.noPlatformPeriod")}</p>}
        </div>
      ),
    },
    monthly: { labelKey: "dashboard.blockMonthly", node: <MonthlyTitles scope={scope} /> },
  };

  // Resolve saved layout → ordered, expert-gated block ids. Saved order first
  // (valid ids only), then any registry blocks the layout doesn't mention.
  const layout = prefs.dashboard_layout || { order: [], hidden: [] };
  const savedOrder = (layout.order || []).filter((x): x is BlockId => (DEFAULT_ORDER as string[]).includes(x));
  const fullOrder: BlockId[] = [...savedOrder, ...DEFAULT_ORDER.filter((id) => !savedOrder.includes(id))];
  const hidden = new Set<string>(layout.hidden || []);
  const gated = fullOrder.filter((id) => !blocks[id].expert || prefs.expert);
  const rendered = editing ? gated : gated.filter((id) => !hidden.has(id));

  const persist = (order: BlockId[], hid: string[]) => {
    savePrefs({ dashboard_layout: { order, hidden: hid } }).catch(() => {});
  };
  const move = (id: BlockId, dir: -1 | 1) => {
    const i = gated.indexOf(id);
    const j = i + dir;
    if (j < 0 || j >= gated.length) return;
    const neighbor = gated[j];
    const order = [...fullOrder];
    const oi = order.indexOf(id), oj = order.indexOf(neighbor);
    [order[oi], order[oj]] = [order[oj], order[oi]];
    persist(order, [...hidden]);
  };
  const toggleHide = (id: BlockId) => {
    const h = new Set(hidden);
    if (h.has(id)) h.delete(id); else h.add(id);
    persist(fullOrder, [...h]);
  };

  return (
    <>
      <div className="section-head">
        <div className="col" style={{ gap: 2 }}>
          <h1 className="large-title">{t("nav.dashboard")}</h1>
          <span className="muted">{t("dashboard.overviewFor", { scope: scopeName })}</span>
        </div>
        <div className="spacer" style={{ flex: 1 }} />
        {editing && <button className="btn-ghost btn-sm" onClick={() => persist([], [])}>{t("dashboard.restoreDefault")}</button>}
        <button className="btn-ghost btn-sm" onClick={() => setEditing((e) => !e)}>
          {editing ? t("dashboard.doneEditing") : t("dashboard.editLayout")}
        </button>
        {!editing && <AddCinemaFilmButton variant="ghost" />}
      </div>

      {rendered.map((id) => {
        if (!editing) return <Fragment key={id}>{blocks[id].node}</Fragment>;
        const gi = gated.indexOf(id);
        return (
          <EditBlock key={id} label={t(blocks[id].labelKey)} hidden={hidden.has(id)}
            first={gi === 0} last={gi === gated.length - 1}
            onUp={() => move(id, -1)} onDown={() => move(id, 1)} onToggle={() => toggleHide(id)}>
            {blocks[id].node}
          </EditBlock>
        );
      })}
    </>
  );
}

// Edit-mode wrapper: a control bar (reorder up/down + hide/show) above each
// block. Hidden blocks stay listed here (dimmed) so they can be toggled back on.
function EditBlock({ label, hidden, first, last, onUp, onDown, onToggle, children }: {
  label: string; hidden: boolean; first: boolean; last: boolean;
  onUp: () => void; onDown: () => void; onToggle: () => void; children: ReactNode;
}) {
  const { t } = useT();
  return (
    <div className={`dash-edit-block ${hidden ? "is-hidden" : ""}`}>
      <div className="dash-edit-bar">
        <span className="dash-edit-label">{label}</span>
        <div className="spacer" style={{ flex: 1 }} />
        <button className="btn-ghost btn-sm dash-edit-btn" disabled={first} onClick={onUp} title={t("dashboard.moveUp")} aria-label={t("dashboard.moveUp")}>
          <IconChevron width={16} height={16} style={{ transform: "rotate(-90deg)" }} />
        </button>
        <button className="btn-ghost btn-sm dash-edit-btn" disabled={last} onClick={onDown} title={t("dashboard.moveDown")} aria-label={t("dashboard.moveDown")}>
          <IconChevron width={16} height={16} style={{ transform: "rotate(90deg)" }} />
        </button>
        <button className="btn-ghost btn-sm dash-edit-btn" onClick={onToggle}
          title={hidden ? t("dashboard.showBlock") : t("dashboard.hideBlock")}
          aria-label={hidden ? t("dashboard.showBlock") : t("dashboard.hideBlock")}>
          {hidden ? <IconEyeOff width={16} height={16} /> : <IconEye width={16} height={16} />}
        </button>
      </div>
      <div className="dash-edit-body">{children}</div>
    </div>
  );
}

// Titles started but not finished — the precomputed "still watching" tracker
// (Expert mode). Rendered as a compact poster grid (identical rhythm to the
// monthly grid so it lines up with the other blocks). Each poster's subtitle
// says what's left: movies show minutes-left + percent watched; series show
// episodes-left + the total time those episodes represent.
function UnfinishedTitles({ scope }: { scope: string }) {
  const { t } = useT();
  const { data, loading, error, reload } = useFetch<any[]>(
    () => api.get("/stats/unfinished", { profile: scope }), [scope]);

  const subtitle = (u: any): string => {
    const minLeft = u.remaining_minutes != null ? t("dashboard.minLeft", { min: u.remaining_minutes }) : null;
    const parts = u.kind === "movie"
      ? [minLeft, t("dashboard.pctWatched", { pct: u.progress ?? 0 })]
      : [t("dashboard.epsLeft", { eps: u.remaining_episodes ?? 0 }), minLeft];
    return parts.filter(Boolean).join(" · ");
  };

  return (
    <Section title={t("dashboard.unfinished")}>
      {loading ? <Loading /> : error ? <ErrorState error={error} retry={reload} /> :
        data && data.length ? (
          <div className="poster-grid">
            {data.map((u: any) => (
              <Poster key={u.id} to={`/title/${u.id}`} poster={u.poster} title={u.title} kind={u.kind}
                enrichId={u.id} subtitle={subtitle(u)}
                badge={u.kind === "movie" ? t("common.film") : t("common.series")} />
            ))}
          </div>
        ) : <p className="muted">{t("dashboard.unfinishedEmpty")}</p>}
    </Section>
  );
}

// Isolated so paging months only re-renders this section (and not the Spark
// chart / per-platform card above it), matching the Overviews experience.
// Mirrors the Overviews "Bekeken per maand" section.
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

// Expert-mode live layer: polls /scrobble/now-playing and shows what is playing
// across the household right now. Renders nothing when Expert mode is off or
// nothing is playing, so it stays invisible for non-expert users.
function NowPlaying({ scope }: { scope: string }) {
  const { prefs } = useApp();
  const { t } = useT();
  const { data, refresh } = useFetch<any[]>(() => api.get("/scrobble/now-playing"), []);

  useEffect(() => {
    if (!prefs.expert) return;
    const id = setInterval(() => { refresh(); }, 5000);
    return () => clearInterval(id);
  }, [prefs.expert, refresh]);

  if (!prefs.expert) return null;
  let items = data || [];
  if (scope !== "all") items = items.filter((s: any) => s.profile_id === scope);
  if (!items.length) return null;

  return (
    <Section title={t("scrobble.nowPlaying")}>
      <div className="card col" style={{ gap: 16, marginBottom: 24 }}>
        {items.map((s: any) => {
          const sub = s.kind === "series" && s.season != null
            ? `S${s.season}·E${s.episode}${s.episode_name ? " · " + s.episode_name : ""}`
            : (s.year ? String(s.year) : "");
          const meta = [s.profile, providerLabel(t, s.provider, s.provider),
            s.state === "paused" ? t("scrobble.paused") : t("scrobble.playing")]
            .filter(Boolean).join(" · ");
          const pct = Math.max(0, Math.min(100, Number(s.progress) || 0));
          const inner = (
            <>
              <div className="poster" style={{ width: 46, flexShrink: 0, aspectRatio: "2 / 3", borderRadius: 8, overflow: "hidden" }}>
                {s.poster ? <img src={s.poster} alt="" loading="lazy" style={{ width: "100%", height: "100%", objectFit: "cover" }} />
                  : <div className="ph" style={{ width: "100%", height: "100%" }} />}
              </div>
              <div className="col" style={{ flex: 1, gap: 4, minWidth: 0 }}>
                <strong style={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{s.title}</strong>
                <span className="caption" style={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                  {sub ? `${sub} · ${meta}` : meta}
                </span>
                <div className="bar-track">
                  <div className="bar-fill" style={{ width: `${pct}%`, background: s.provider_color || "var(--accent)" }} />
                </div>
              </div>
              <span className="caption" style={{ flexShrink: 0, width: 42, textAlign: "right" }}>{Math.round(pct)}%</span>
            </>
          );
          return s.title_id ? (
            <Link key={s.id} to={`/title/${s.title_id}`} className="row np-row" style={{ gap: 14, alignItems: "center" }}>
              {inner}
            </Link>
          ) : (
            <div key={s.id} className="row" style={{ gap: 14, alignItems: "center" }}>
              {inner}
            </div>
          );
        })}
      </div>
    </Section>
  );
}
