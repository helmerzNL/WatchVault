import { useState, useEffect, useRef, Fragment, type ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useApp } from "../lib/app";
import { useT, providerLabel, mediaBadge, watchedSubtitle } from "../lib/i18n";
import { api } from "../lib/api";
import { useFetch } from "../lib/useFetch";
import { Spark } from "../components/charts";
import { Loading, ErrorState, Empty, Stat, Poster, Section, MonthNav, RangeSeg, Seg, type Range } from "../components/ui";
import { fmtHours, fmtNum, fmtMonth, fmtDayMonth, monthKey, monthLabel } from "../lib/format";
import { IconChart, IconImport, IconLayout, IconCheck, IconRefresh } from "../components/icons";
import { AddCinemaFilmButton } from "../components/AddCinemaFilm";
import { EpisodePicker } from "../components/EpisodePicker";
import { resolveLayout, EditBlock } from "../components/LayoutEdit";
import { WatchedGrid } from "../components/WatchedGrid";

type RecentRange = "week" | "month" | "year";

// Dashboard blocks are a registry so the layout can be reordered / hidden per
// user (persisted in prefs.dashboard_layout, synced via /preferences). Blocks
// marked `expert` only appear when Expert mode is on. Unknown/new ids in a saved
// layout are ignored and new blocks are appended, so old layouts stay valid.
type BlockId = "nowPlaying" | "unfinished" | "unknown" | "stats" | "trend" | "platforms" | "monthly";
const DEFAULT_ORDER: BlockId[] = ["nowPlaying", "unfinished", "unknown", "stats", "trend", "platforms", "monthly"];

export function Dashboard() {
  const { scope, user, profiles, prefs, savePrefs } = useApp();
  const { t } = useT();
  const [range, setRange] = useState<Range>("all");
  const [recentRange, setRecentRange] = useState<RecentRange>("month");
  const [editing, setEditing] = useState(false);
  const [dragId, setDragId] = useState<BlockId | null>(null);
  const [overId, setOverId] = useState<BlockId | null>(null);

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

  const scopeName = scope === "all"
    ? (user?.household_name || t("dashboard.theHousehold"))
    : (profiles.find((p) => p.id === scope)?.display_name || t("dashboard.thisProfile"));

  const blocks: Record<BlockId, { labelKey: string; expert?: boolean; node: ReactNode }> = {
    nowPlaying: { labelKey: "dashboard.blockNowPlaying", expert: true, node: <NowPlaying scope={scope} /> },
    unfinished: { labelKey: "dashboard.blockUnfinished", expert: true, node: <UnfinishedTitles scope={scope} /> },
    unknown: { labelKey: "dashboard.blockUnknown", node: <UnknownTitles scope={scope} /> },
    stats: {
      labelKey: "dashboard.blockStats",
      node: <StatsBlock s={s} editing={editing} />,
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

  // Resolve saved layout → ordered, expert-gated block ids via the shared
  // layout helper (same logic used by the stat tiles and the Overviews page).
  const dl = prefs.dashboard_layout || { order: [], hidden: [] };
  const blockCtrl = resolveLayout<BlockId>({
    editing,
    defaultOrder: DEFAULT_ORDER,
    stored: dl,
    gate: (id) => !blocks[id].expert || !!prefs.expert,
    persist: (order, hidden) => {
      savePrefs({ dashboard_layout: { ...dl, order, hidden } }).catch(() => {});
    },
    drag: { dragId, overId, setDragId, setOverId },
  });

  // Restore default resets the dashboard blocks AND the stat-tile layout (both
  // editable here); the Overviews layout has its own restore on that page.
  const restoreDefault = () => {
    savePrefs({ dashboard_layout: { ...dl, order: [], hidden: [], stats: { order: [], hidden: [] } } }).catch(() => {});
  };

  return (
    <>
      <div className="section-head">
        <div className="col" style={{ gap: 2 }}>
          <h1 className="large-title">{t("nav.dashboard")}</h1>
          <span className="muted">{t("dashboard.overviewOf", { name: scopeName })}</span>
        </div>
        <div className="spacer" style={{ flex: 1 }} />
        {editing && <button className="btn-ghost btn-sm" onClick={restoreDefault}
          title={t("dashboard.restoreDefault")} aria-label={t("dashboard.restoreDefault")}>
          <IconRefresh width={18} height={18} />
        </button>}
        <button className={`btn-ghost btn-sm dash-edit-toggle ${editing ? "is-active" : ""}`} onClick={() => setEditing((e) => !e)}
          title={editing ? t("dashboard.doneEditing") : t("dashboard.editLayout")}
          aria-label={editing ? t("dashboard.doneEditing") : t("dashboard.editLayout")}>
          {editing ? <IconCheck width={18} height={18} /> : <IconLayout width={18} height={18} />}
        </button>
        {!editing && <AddCinemaFilmButton variant="ghost" />}
      </div>

      {blockCtrl.shown.map((id) => {
        if (!editing) return <Fragment key={id}>{blocks[id].node}</Fragment>;
        return (
          <EditBlock key={id} id={id} label={t(blocks[id].labelKey)} ctrl={blockCtrl}>
            {blocks[id].node}
          </EditBlock>
        );
      })}
    </>
  );
}

// The totals grid, with per-tile hide + drag reorder while the dashboard is in
// edit mode (mirrors the block-level editing, one level deeper). Layout is
// stored under prefs.dashboard_layout.stats and synced via /preferences. The
// two "remaining" tiles are Expert-only. Not editing → a plain stat grid with
// consistent top/bottom whitespace so it doesn't butt against the block above.
type StatId = "hours" | "titles" | "movies" | "episodes" | "remaining" | "remainingItems";
const STATS_ORDER: StatId[] = ["hours", "titles", "movies", "episodes", "remaining", "remainingItems"];

function StatsBlock({ s, editing }: { s: any; editing: boolean }) {
  const { t } = useT();
  const { prefs, savePrefs } = useApp();
  const [dragId, setDragId] = useState<StatId | null>(null);
  const [overId, setOverId] = useState<StatId | null>(null);

  const tiles: Record<StatId, { expert?: boolean; node: ReactNode }> = {
    hours: { node: <Stat value={fmtHours(s.totals.hours)} label={t("dashboard.totalWatchTime")} /> },
    titles: { node: <Stat value={fmtNum(s.totals.titles)} label={t("dashboard.uniqueTitles")} /> },
    movies: { node: <Stat value={fmtNum(s.totals.movies)} label={t("common.movies")} /> },
    episodes: { node: <Stat value={fmtNum(s.totals.episodes)} label={t("common.episodes")} /> },
    remaining: { expert: true, node: <Stat value={fmtHours((s.totals.remaining_minutes || 0) / 60)} label={t("dashboard.stillToWatch")} /> },
    remainingItems: { expert: true, node: <Stat value={fmtNum(s.totals.remaining_items || 0)} label={t("dashboard.itemsUnfinished")} /> },
  };

  const dl = prefs.dashboard_layout || { order: [], hidden: [] };
  const ctrl = resolveLayout<StatId>({
    editing,
    defaultOrder: STATS_ORDER,
    stored: dl.stats,
    gate: (id) => !tiles[id].expert || !!prefs.expert,
    persist: (order, hidden) => {
      savePrefs({ dashboard_layout: { ...dl, stats: { order, hidden } } }).catch(() => {});
    },
    drag: { dragId, overId, setDragId, setOverId },
  });

  return (
    <div className={`stat-grid ${editing ? "" : "dash-stats"}`}>
      {ctrl.shown.map((id) => (
        editing
          ? <EditBlock key={id} id={id} ctrl={ctrl} compact>{tiles[id].node}</EditBlock>
          : <Fragment key={id}>{tiles[id].node}</Fragment>
      ))}
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
    if (u.kind === "movie")
      return [minLeft, t("dashboard.pctWatched", { pct: u.progress ?? 0 })].filter(Boolean).join(" · ");
    const eps = t("dashboard.epsLeft", { eps: u.remaining_episodes ?? 0 });
    return minLeft ? `${minLeft} (${eps})` : eps;
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

// The "Unknown" bucket: titles that could not be identified as episodic series
// (no recognized season/episode). Gathering them here keeps them out of the
// "still to watch" tracker while still giving a place to find and manage them.
function UnknownTitles({ scope }: { scope: string }) {
  const { t } = useT();
  const { data, loading, error, reload } = useFetch<any[]>(
    () => api.get("/stats/unknown", { profile: scope }), [scope]);

  return (
    <Section title={t("dashboard.unknown")}
      right={data && data.length ? <Link to="/search?kind=unknown" className="btn-ghost btn-sm">{t("dashboard.unknownViewAll")}</Link> : undefined}>
      {loading ? <Loading /> : error ? <ErrorState error={error} retry={reload} /> :
        data && data.length ? (
          <div className="poster-grid">
            {data.map((u: any) => (
              <Poster key={u.id} to={`/title/${u.id}`} poster={u.poster} title={u.title} kind={u.kind}
                enrichId={u.id} unknown
                subtitle={u.events > 1 ? t("dashboard.unknownSeen", { count: u.events }) : (u.year ? String(u.year) : "")}
                badge={t("common.unknown")} />
            ))}
          </div>
        ) : <p className="muted">{t("dashboard.unknownEmpty")}</p>}
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
          <WatchedGrid items={data} posKey="month"
            subtitle={(t2) => watchedSubtitle(t, t2)}
            badge={(t2) => mediaBadge(t, t2)} />
        ) : <p className="muted">{t("overviews.nothingIn", { month: monthLabel(month) })}</p>}
    </Section>
  );
}

// Expert-mode live layer: polls /scrobble/now-playing and shows what is playing
// across the household right now. Renders nothing when Expert mode is off or
// nothing is playing, so it stays invisible for non-expert users.
// Providers whose HA push carries only a show title (no S/E): a long-press on the
// Now-playing row opens a TMDB-driven picker to bind the concrete episode.
const PICK_PROVIDERS = ["skyshowtime", "videoland"];

// A Now-playing row that navigates on tap/click but opens the episode picker on a
// ~500ms long-press (cancelled if the pointer moves, so scrolling still works).
function LongPressRow({ inner, onOpen, onNavigate }: {
  inner: ReactNode; onOpen: () => void; onNavigate: () => void;
}) {
  const timer = useRef<number | null>(null);
  const start = useRef<{ x: number; y: number } | null>(null);
  const longFired = useRef(false);
  const clear = () => { if (timer.current) { clearTimeout(timer.current); timer.current = null; } };
  return (
    <div className="row np-row" role="link" tabIndex={0}
      style={{ gap: 14, alignItems: "center", cursor: "pointer", userSelect: "none", WebkitUserSelect: "none", touchAction: "pan-y" }}
      onPointerDown={(e) => {
        longFired.current = false;
        start.current = { x: e.clientX, y: e.clientY };
        clear();
        timer.current = window.setTimeout(() => { longFired.current = true; onOpen(); }, 500);
      }}
      onPointerMove={(e) => {
        if (!start.current) return;
        if (Math.abs(e.clientX - start.current.x) > 12 || Math.abs(e.clientY - start.current.y) > 12) clear();
      }}
      onPointerUp={() => { clear(); if (!longFired.current) onNavigate(); start.current = null; }}
      onPointerLeave={clear}
      onPointerCancel={() => { clear(); longFired.current = false; }}
      onContextMenu={(e) => e.preventDefault()}
      onKeyDown={(e) => { if (e.key === "Enter") onNavigate(); }}>
      {inner}
    </div>
  );
}

function NowPlaying({ scope }: { scope: string }) {
  const { prefs } = useApp();
  const { t } = useT();
  const navigate = useNavigate();
  const [picker, setPicker] = useState<any | null>(null);
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
          const eligible = s.title_id && PICK_PROVIDERS.includes(s.provider_key);
          if (eligible) {
            return (
              <LongPressRow key={s.id} inner={inner}
                onOpen={() => setPicker(s)}
                onNavigate={() => navigate(`/title/${s.title_id}`)} />
            );
          }
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
      {picker && (
        <EpisodePicker session={picker} onClose={() => setPicker(null)} onSaved={refresh} />
      )}
    </Section>
  );
}
