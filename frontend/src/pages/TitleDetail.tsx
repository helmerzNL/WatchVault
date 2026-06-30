import { useParams, Link } from "react-router-dom";
import { useApp } from "../lib/app";
import { useT, useGenre } from "../lib/i18n";
import { api, ApiError } from "../lib/api";
import { useFetch } from "../lib/useFetch";
import { Loading, ErrorState, BackLink } from "../components/ui";
import { IconSparkles, IconCheck, IconRefresh, IconPlus, IconClose } from "../components/icons";
import { fmtDate } from "../lib/format";
import { useState } from "react";

const today = () => new Date().toISOString().slice(0, 10);

type ManualWatch = { id: string; date: string };

function PersonCard({ c }: { c: any }) {
  const inner = (
    <>
      <span className="avatar" style={{ width: 56, height: 56 }}>
        {c.profile ? <img src={c.profile} alt="" /> : (c.name?.[0] || "?")}
      </span>
      <span className="caption" style={{ fontWeight: 600, color: "var(--text)" }}>{c.name}</span>
      {(c.character || c.job) && <span className="caption">{c.character || c.job}</span>}
    </>
  );
  return c.id
    ? <Link to={`/person/${c.id}`} className="cast-card" style={{ textDecoration: "none" }}>{inner}</Link>
    : <div className="cast-card">{inner}</div>;
}

// Inline "add a watch date" control: a + button that reveals a date picker
// (defaulting to today) with confirm/cancel. Used for movies and episodes.
function AddWatch({ onAdd, label }: { onAdd: (date: string) => Promise<void>; label?: string }) {
  const { t } = useT();
  const [open, setOpen] = useState(false);
  const [date, setDate] = useState(today);
  const [busy, setBusy] = useState(false);
  if (!open) {
    return (
      <button className="btn-ghost btn-sm" onClick={() => { setDate(today()); setOpen(true); }}>
        <IconPlus width={14} height={14} /> {label || t("title.addWatch")}
      </button>
    );
  }
  return (
    <div className="row" style={{ gap: 6, alignItems: "center" }}>
      <input type="date" value={date} max={today()}
        onChange={(e) => setDate(e.target.value)} style={{ minHeight: 34, padding: "4px 8px" }} />
      <button className="btn-primary btn-sm" disabled={busy || !date}
        onClick={async () => { setBusy(true); try { await onAdd(date); setOpen(false); } finally { setBusy(false); } }}>
        {t("common.add")}
      </button>
      <button className="btn-ghost btn-sm" onClick={() => setOpen(false)}>{t("common.cancel")}</button>
    </div>
  );
}

// Removable chips for hand-entered watch dates.
function ManualDates({ items, onRemove }: { items: ManualWatch[]; onRemove: (id: string) => void }) {
  const { t } = useT();
  if (!items?.length) return null;
  return (
    <div className="row wrap" style={{ gap: 6 }}>
      {items.map((w) => (
        <span key={w.id} className="chip" style={{ minHeight: 0, padding: "3px 6px 3px 10px", gap: 4 }}>
          {fmtDate(w.date)}
          <button className="manual-x" title={t("common.remove")} aria-label={t("common.remove")}
            onClick={() => onRemove(w.id)}>
            <IconClose width={12} height={12} />
          </button>
        </span>
      ))}
    </div>
  );
}

type Ctl = {
  canEdit: boolean;
  addEpisode: (episodeId: string, date: string) => Promise<void>;
  addSeason: (season: number, date: string) => Promise<void>;
  removeWatch: (eventId: string) => void;
};

function EpisodeRow({ ep, ctl }: { ep: any; ctl: Ctl }) {
  const { t } = useT();
  const meta: string[] = [];
  if (ep.air_date) meta.push(fmtDate(ep.air_date));
  if (ep.runtime_minutes) meta.push(t("title.min", { n: ep.runtime_minutes }));
  const dates: string[] = ep.watch_dates?.length ? ep.watch_dates : (ep.last_watched ? [ep.last_watched] : []);
  return (
    <div className={`episode-row ${ep.watched ? "is-watched" : ""}`}>
      <div className="episode-still">
        {ep.still ? <img src={ep.still} alt="" loading="lazy" /> : <span className="episode-still-ph">{ep.episode}</span>}
        {ep.watched && <span className="episode-check" title={t("title.watched")}><IconCheck width={14} height={14} /></span>}
      </div>
      <div className="episode-body">
        <div className="episode-head">
          <span className="episode-num">{ep.episode}</span>
          <strong className="episode-name">{ep.name || t("title.episodeN", { n: ep.episode })}</strong>
        </div>
        {meta.length > 0 && <span className="caption">{meta.join(" · ")}</span>}
        {ep.overview && <p className="episode-overview">{ep.overview}</p>}
        <span className={`episode-status ${ep.watched ? "on" : ""}`}>
          {dates.length > 0
            ? t("title.watchedOn", { date: dates.map((d) => fmtDate(d)).join(" · ") })
            : t("title.notWatched")}
        </span>
        {ctl.canEdit && (
          <div className="manual-row">
            {ep.manual_watches?.length > 0 && (
              <ManualDates items={ep.manual_watches} onRemove={ctl.removeWatch} />
            )}
            <AddWatch onAdd={(date) => ctl.addEpisode(ep.id, date)}
              label={ep.watched ? t("title.addWatch") : t("title.markWatched")} />
          </div>
        )}
      </div>
    </div>
  );
}

function Seasons({ seasons, ctl }: { seasons: any[]; ctl: Ctl }) {
  const { t } = useT();
  const [active, setActive] = useState(seasons[0]?.season ?? 0);
  const current = seasons.find((s) => s.season === active) || seasons[0];
  if (!current) return null;
  const pct = current.episode_count ? Math.round((current.watched_count / current.episode_count) * 100) : 0;

  return (
    <>
      <h2 className="title" style={{ margin: "28px 0 14px" }}>{t("title.episodes")}</h2>
      {seasons.length > 1 && (
        <div className="season-tabs">
          {seasons.map((s) => (
            <button key={s.season}
              className={`chip ${s.season === active ? "active" : ""}`}
              onClick={() => setActive(s.season)}>
              {s.season === 0 ? t("title.specials") : t("title.seasonN", { n: s.season })}
              <span className="season-tab-count">{s.watched_count}/{s.episode_count}</span>
            </button>
          ))}
        </div>
      )}
      <div className="card season-panel">
        <div className="season-progress">
          <div className="row" style={{ gap: 10 }}>
            <strong>{current.season === 0 ? t("title.specials") : t("title.seasonN", { n: current.season })}</strong>
            <span className="caption">{t("title.watchedOfEpisodes", { watched: current.watched_count, total: current.episode_count })}</span>
            <div className="spacer" style={{ flex: 1 }} />
            <span className="caption" style={{ fontWeight: 700, color: "var(--accent)" }}>{pct}%</span>
          </div>
          <div className="bar-track" style={{ marginTop: 8 }}>
            <div className="bar-fill" style={{ width: `${pct}%` }} />
          </div>
          {ctl.canEdit && (
            <div style={{ marginTop: 10 }}>
              <AddWatch onAdd={(date) => ctl.addSeason(current.season, date)}
                label={t("title.markSeasonWatched")} />
            </div>
          )}
        </div>
        <div className="episode-list">
          {current.episodes.map((ep: any) => <EpisodeRow key={ep.id} ep={ep} ctl={ctl} />)}
        </div>
      </div>
    </>
  );
}

export function TitleDetail() {
  const { id } = useParams();
  const { scope, can, toast } = useApp();
  const { t, lang } = useT();
  const tGenre = useGenre();
  const { data: ti, loading, error, reload } = useFetch<any>(
    () => api.get(`/search/title/${id}`, { profile: scope, lang }), [id, scope, lang]);
  const [enriching, setEnriching] = useState(false);
  const [syncingTrakt, setSyncingTrakt] = useState(false);

  const canEdit = can("ingest.write");
  const targetBody = () => (scope && scope !== "all" ? { user_id: scope } : {});

  if (loading) return <Loading />;
  if (error) return <ErrorState error={error} retry={reload} />;
  if (!ti) return null;

  async function enrich() {
    setEnriching(true);
    try {
      const res = await api.post(`/titles/${id}/enrich`);
      const ok = res.status === "enriched";
      toast(ok ? t("title.enriched") : t("title.couldntEnrich", { status: res.status || "no match" }), ok ? "ok" : "err");
      reload();
    } catch (e) { toast(e instanceof ApiError ? e.message : t("settings.failed"), "err"); }
    finally { setEnriching(false); }
  }

  async function syncTrakt() {
    setSyncingTrakt(true);
    try {
      const res = await api.post(`/titles/${id}/trakt-sync`, targetBody());
      const added = res.inserted || 0;
      toast(added > 0 ? t("title.traktSynced", { n: added }) : t("title.traktNothing"), "ok");
      reload();
    } catch (e) { toast(e instanceof ApiError ? e.message : t("settings.failed"), "err"); }
    finally { setSyncingTrakt(false); }
  }

  async function addTitleWatch(date: string) {
    try {
      await api.post(`/titles/${id}/watch`, { ...targetBody(), date });
      toast(t("title.watchAdded"), "ok");
      reload();
    } catch (e) { toast(e instanceof ApiError ? e.message : t("settings.failed"), "err"); }
  }

  const ctl: Ctl = {
    canEdit,
    addEpisode: async (episodeId, date) => {
      try {
        await api.post(`/episodes/${episodeId}/watch`, { ...targetBody(), date });
        toast(t("title.watchAdded"), "ok");
        reload();
      } catch (e) { toast(e instanceof ApiError ? e.message : t("settings.failed"), "err"); }
    },
    addSeason: async (season, date) => {
      try {
        const res = await api.post(`/titles/${id}/seasons/${season}/watch`, { ...targetBody(), date });
        toast(t("title.seasonMarked", { n: res.inserted || 0 }), "ok");
        reload();
      } catch (e) { toast(e instanceof ApiError ? e.message : t("settings.failed"), "err"); }
    },
    removeWatch: async (eventId) => {
      try {
        await api.del(`/watch-events/${eventId}`);
        toast(t("title.watchRemoved"), "ok");
        reload();
      } catch (e) { toast(e instanceof ApiError ? e.message : t("settings.failed"), "err"); }
    },
  };

  return (
    <>
      <BackLink />

      <div className="title-hero card" style={ti.backdrop ? {
        backgroundImage: `linear-gradient(to top, var(--bg-elev), rgba(0,0,0,0.1)), url(${ti.backdrop})`,
        backgroundSize: "cover", backgroundPosition: "center",
      } : undefined}>
        <div className="row" style={{ gap: 20, alignItems: "flex-end" }}>
          <div className="poster" style={{ width: 130, flexShrink: 0 }}>
            {ti.poster ? <img src={ti.poster} alt={ti.title} /> : <div className="ph">{ti.title}</div>}
          </div>
          <div className="col" style={{ gap: 8 }}>
            <h1 className="large-title">{ti.title}</h1>
            <div className="row wrap" style={{ gap: 8 }}>
              <span className="chip" style={{ minHeight: 0, padding: "2px 10px" }}>{ti.kind === "movie" ? t("common.film") : t("common.series")}</span>
              {ti.year && <span className="chip" style={{ minHeight: 0, padding: "2px 10px" }}>{ti.year}</span>}
              {ti.runtime_minutes && <span className="chip" style={{ minHeight: 0, padding: "2px 10px" }}>{t("title.min", { n: ti.runtime_minutes })}</span>}
            </div>
            <div className="chips">{ti.genres?.map((g: string) => <span key={g} className="chip">{tGenre(g)}</span>)}</div>
          </div>
        </div>
      </div>

      {ti.overview && <p className="muted" style={{ margin: "20px 0" }}>{ti.overview}</p>}

      {canEdit && (
        <div className="row wrap" style={{ gap: 10, marginBottom: 20 }}>
          <button className="btn-ghost btn-sm" disabled={enriching} onClick={enrich}>
            <IconSparkles width={16} height={16} /> {enriching ? t("title.enriching") : t("title.enrichTmdb")}
          </button>
          {ti.trakt_configured && (
            <button className="btn-ghost btn-sm" disabled={syncingTrakt} onClick={syncTrakt}>
              <IconRefresh width={16} height={16} /> {syncingTrakt ? t("title.syncingTrakt") : t("title.syncTrakt")}
            </button>
          )}
        </div>
      )}

      {/* Manual watch dates for a movie (series mark watched per season/episode). */}
      {canEdit && ti.kind === "movie" && (
        <div className="card" style={{ marginBottom: 20 }}>
          <div className="row wrap" style={{ gap: 12, alignItems: "center" }}>
            <strong>{t("title.watchDates")}</strong>
            <ManualDates items={ti.manual_watches || []} onRemove={ctl.removeWatch} />
            <div className="spacer" style={{ flex: 1 }} />
            <AddWatch onAdd={addTitleWatch}
              label={ti.manual_watches?.length ? t("title.addWatch") : t("title.markWatched")} />
          </div>
        </div>
      )}

      {ti.kind === "series" && ti.seasons?.length > 0 && <Seasons seasons={ti.seasons} ctl={ctl} />}

      {ti.cast?.length > 0 && (
        <>
          <h2 className="title" style={{ margin: "8px 0 14px" }}>{t("common.cast")}</h2>
          <div className="cast-row">
            {ti.cast.map((c: any, i: number) => <PersonCard key={c.id || i} c={c} />)}
          </div>
        </>
      )}

      {ti.crew?.length > 0 && (
        <>
          <h2 className="title" style={{ margin: "28px 0 14px" }}>{t("common.crew")}</h2>
          <div className="cast-row">
            {ti.crew.map((c: any, i: number) => <PersonCard key={c.id || i} c={c} />)}
          </div>
        </>
      )}

      {ti.events?.length > 0 && (
        <>
          <h2 className="title" style={{ margin: "28px 0 14px" }}>{t("title.watchHistory")}</h2>
          <div className="card">
            {ti.events.map((e: any, i: number) => (
              <div key={i} className="list-row">
                <div className="col" style={{ flex: 1, gap: 2 }}>
                  <strong>
                    {e.kind === "episode" && e.season != null
                      ? `S${e.season}${e.episode != null ? `E${e.episode}` : ""}${e.raw_title ? " · " + e.raw_title : ""}`
                      : e.raw_title || ti.title}
                  </strong>
                  <span className="caption">{e.platform} · {e.who}</span>
                </div>
                <span className="caption">{fmtDate(e.date)}</span>
              </div>
            ))}
          </div>
        </>
      )}
    </>
  );
}
