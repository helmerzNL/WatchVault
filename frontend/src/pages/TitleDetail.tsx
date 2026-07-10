import { useParams, useSearchParams, Link } from "react-router-dom";
import { useApp } from "../lib/app";
import { useT, useGenre, providerLabel, mediaBadge } from "../lib/i18n";
import { api, ApiError } from "../lib/api";
import { useFetch } from "../lib/useFetch";
import { Loading, ErrorState, BackLink } from "../components/ui";
import { TagChips } from "../components/TagChips";
import { IconSparkles, IconCheck, IconRefresh, IconPlus, IconClose, IconPencil } from "../components/icons";
import { fmtDate, todayLocalKey, localDateKey, fmtNum, fmtDurationHM } from "../lib/format";
import { useState, useEffect, useRef } from "react";

const today = () => todayLocalKey();
const yesterday = () => {
  const d = new Date();
  d.setDate(d.getDate() - 1);
  return localDateKey(d);
};

// A network/broadcaster logo (from TMDB) shown on its own — no name beside it.
// TMDB only ships one logo per network, so to keep every logo legible in both
// the light and dark themes we sample the logo's average brightness (its pixels
// are served with CORS) and give it a CONTRASTING backing plate: a light plate
// behind dark logos, a dark plate behind light ones. If sampling is blocked we
// keep the default light plate, which suits the typically-dark TMDB logos.
// Falls back to a name chip when a network has no logo.
function NetworkLogo({ logo, name }: { logo?: string; name: string }) {
  const [tone, setTone] = useState<"dark" | "light">("dark");
  const [failed, setFailed] = useState(false);

  // Brightness sampling is best-effort and kept OFF the visible <img>: reading
  // pixels needs a CORS-clean image, but the service worker caches TMDB images
  // as opaque responses (CacheFirst), which would taint the canvas — and forcing
  // crossOrigin on the visible image makes it fail to render entirely. So we
  // probe a separate off-DOM image for the tone and silently keep the default
  // when reading is blocked.
  useEffect(() => {
    setFailed(false);
    if (!logo) return;
    let cancelled = false;
    const probe = new Image();
    probe.crossOrigin = "anonymous";
    probe.onload = () => {
      if (cancelled) return;
      try {
        const c = document.createElement("canvas");
        const w = (c.width = 28), h = (c.height = 28);
        const ctx = c.getContext("2d", { willReadFrequently: true });
        if (!ctx) return;
        ctx.drawImage(probe, 0, 0, w, h);
        const { data } = ctx.getImageData(0, 0, w, h);
        let lum = 0, weight = 0;
        for (let i = 0; i < data.length; i += 4) {
          const a = data[i + 3] / 255;
          if (a < 0.12) continue; // ignore (near-)transparent pixels
          lum += (0.2126 * data[i] + 0.7152 * data[i + 1] + 0.0722 * data[i + 2]) * a;
          weight += a;
        }
        if (weight > 0) setTone(lum / weight < 130 ? "dark" : "light");
      } catch {
        /* tainted/opaque canvas — keep the default tone */
      }
    };
    probe.onerror = () => { /* sampling blocked — keep the default tone */ };
    probe.src = logo;
    return () => { cancelled = true; };
  }, [logo]);

  if (!logo || failed) {
    return <span className="chip" style={{ minHeight: 0, padding: "2px 10px" }}>{name}</span>;
  }
  // The visible logo carries no crossOrigin, so it loads exactly like every other
  // poster (including via the SW cache); onError degrades to a readable name chip.
  return (
    <span className={`network-logo network-logo--${tone}`} title={name}>
      <img src={logo} alt={name} onError={() => setFailed(true)} />
    </span>
  );
}

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

// Inline "add a watch date" control: a + button that reveals quick-pick shortcuts
// (release date / yesterday / today) plus a date picker for any other day. Used
// for movies and episodes; `releaseDate` (movie release / episode air date) is
// optional and its shortcut only shows when known and not in the future.
function AddWatch(
  { onAdd, label, releaseDate }:
  { onAdd: (date: string) => Promise<void>; label?: string; releaseDate?: string | null },
) {
  const { t } = useT();
  const [open, setOpen] = useState(false);
  const [date, setDate] = useState(today);
  const [busy, setBusy] = useState(false);
  const td = today();
  async function submit(d: string) {
    setBusy(true);
    try { await onAdd(d); setOpen(false); } finally { setBusy(false); }
  }
  if (!open) {
    return (
      <button className="btn-ghost btn-sm" onClick={() => { setDate(td); setOpen(true); }}>
        <IconPlus width={14} height={14} /> {label || t("title.addWatch")}
      </button>
    );
  }
  return (
    <div className="col" style={{ gap: 6, alignItems: "flex-start" }}>
      <div className="row wrap" style={{ gap: 6 }}>
        {releaseDate && releaseDate <= td && (
          <button className="chip" style={{ minHeight: 0, padding: "4px 10px" }}
            disabled={busy} onClick={() => submit(releaseDate)}>{t("title.releaseDate")}</button>
        )}
        <button className="chip" style={{ minHeight: 0, padding: "4px 10px" }}
          disabled={busy} onClick={() => submit(yesterday())}>{t("common.yesterday")}</button>
        <button className="chip" style={{ minHeight: 0, padding: "4px 10px" }}
          disabled={busy} onClick={() => submit(td)}>{t("common.today")}</button>
      </div>
      <div className="row" style={{ gap: 6, alignItems: "center" }}>
        <input type="date" value={date} max={td}
          onChange={(e) => setDate(e.target.value)} style={{ minHeight: 34, padding: "4px 8px" }} />
        <button className="btn-primary btn-sm" disabled={busy || !date}
          onClick={() => submit(date)}>{t("common.add")}</button>
        <button className="btn-ghost btn-sm" onClick={() => setOpen(false)}>{t("common.cancel")}</button>
      </div>
    </div>
  );
}

// Removable chips for watch dates (any source). Removing a synced date tombstones
// it so a later sync won't bring it back; removing a manual date deletes it.
function WatchDateChips({ dates, onRemove }: { dates: string[]; onRemove: (date: string) => void }) {
  const { t } = useT();
  if (!dates?.length) return null;
  return (
    <div className="row wrap" style={{ gap: 6 }}>
      {dates.map((d) => (
        <span key={d} className="chip" style={{ minHeight: 0, padding: "3px 6px 3px 10px", gap: 4 }}>
          {fmtDate(d)}
          <button className="manual-x" title={t("common.remove")} aria-label={t("common.remove")}
            onClick={() => onRemove(d)}>
            <IconClose width={12} height={12} />
          </button>
        </span>
      ))}
    </div>
  );
}

// Per-title platform override: forces the title's soft (Trakt + manual) events
// onto a chosen provider — e.g. "Cinema" — instead of the auto network guess.
// "Auto" clears the override. Real digital syncs (Plex/Netflix/...) are unaffected.
function PlatformSelect(
  { value, providers, onChange }:
  { value: string; providers: any[]; onChange: (providerId: string) => void },
) {
  const { t } = useT();
  return (
    <label className="row" style={{ gap: 6, alignItems: "center" }}>
      <span className="caption">{t("title.platform")}:</span>
      <select value={value} onChange={(e) => onChange(e.target.value)}
        style={{ minHeight: 34, padding: "4px 8px" }}>
        <option value="">{t("title.platformAuto")}</option>
        {providers.map((p) => (
          <option key={p.id} value={p.id}>{providerLabel(t, p.key, p.name)}</option>
        ))}
      </select>
    </label>
  );
}

// Build the platform-override dropdown: hide Cinema for non-movies and fold
// Plex + Jellyfin into a single "Digital Library" entry (represented by the
// first such provider's id). Also remaps the currently-selected value so a
// Plex/Jellyfin override still shows the merged option as selected.
function platformDropdown(providers: any[], kind: string, currentId: string) {
  const visible = (providers || []).filter(
    (p: any) => p.key !== "cinema" || kind === "movie");
  const options: any[] = [];
  let digitalRepId: string | null = null;
  for (const p of visible) {
    if (p.key === "plex" || p.key === "jellyfin") {
      if (digitalRepId) continue;
      digitalRepId = p.id;
      options.push({ ...p, key: "digital_library" });
    } else {
      options.push(p);
    }
  }
  let value = currentId;
  const cur = (providers || []).find((p: any) => p.id === currentId);
  if (cur && (cur.key === "plex" || cur.key === "jellyfin") && digitalRepId) {
    value = digitalRepId;
  }
  return { options, value };
}

type Ctl = {
  canEdit: boolean;
  titleId: string;
  reload: () => void;
  addEpisode: (episodeId: string, date: string) => Promise<void>;
  addSeason: (season: number, date: string) => Promise<void>;
  removeEpisode: (episodeId: string, date: string) => void;
};

// Live progress bar mirrored from the dashboard's Now playing, rendered on the
// title/episode it belongs to. `compact` trims it for an episode row; the full
// variant sits in its own card for a movie.
function LiveNowBar({ live, compact }: { live: any; compact?: boolean }) {
  const { t } = useT();
  const pct = Math.max(0, Math.min(100, Number(live.progress) || 0));
  const stopped = live.state === "stopped";
  const label = stopped ? t("scrobble.lastPosition") : t("scrobble.nowPlaying");
  const state = live.state === "paused" ? t("scrobble.paused")
    : stopped ? t("scrobble.stopped") : t("scrobble.playing");
  const dotClass = stopped ? "is-stopped" : live.state === "paused" ? "is-paused" : "";
  const meta = [providerLabel(t, live.provider, live.provider), live.profile]
    .filter(Boolean).join(" · ");
  const bar = (
    <div className={`live-now-bar ${stopped ? "is-stopped" : ""}`}>
      <div className="live-now-head">
        <span className={`live-dot ${dotClass}`} />
        <span className="live-now-label">{label}</span>
        <span className="caption" style={{ marginLeft: "auto" }}>
          {stopped
            ? `${Math.round(pct)}%${live.updated_at ? ` (${fmtDate(live.updated_at)})` : ""}`
            : `${state} · ${Math.round(pct)}%`}
        </span>
      </div>
      <div className="bar-track">
        <div className="bar-fill" style={{ width: `${pct}%`, background: live.provider_color || "var(--accent)" }} />
      </div>
      {!compact && meta && <span className="caption">{meta}</span>}
    </div>
  );
  return compact ? bar : <div className="card live-now-card">{bar}</div>;
}

function EpisodeRow({ ep, ctl, live }: { ep: any; ctl: Ctl; live?: any }) {
  const { t } = useT();
  const meta: string[] = [];
  if (ep.air_date) meta.push(fmtDate(ep.air_date));
  if (ep.runtime_minutes) meta.push(t("title.min", { n: ep.runtime_minutes }));
  const dates: string[] = ep.watch_dates?.length ? ep.watch_dates : (ep.last_watched ? [ep.last_watched] : []);
  return (
    <div className={`episode-row ${ep.watched ? "is-watched" : ""} ${live ? "is-live" : ""}`}>
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
        {live && <LiveNowBar live={live} compact />}
        <TagChips tags={ep.tags || []} canEdit={ctl.canEdit}
          attach={(tagId) => api.post(`/episodes/${ep.id}/tags/${tagId}`)}
          detach={(tagId) => api.del(`/episodes/${ep.id}/tags/${tagId}`)}
          onChange={ctl.reload} />
        {(!ctl.canEdit || dates.length === 0) && (
          <span className={`episode-status ${ep.watched ? "on" : ""}`}>
            {dates.length > 0
              ? t("title.watchedOn", { date: dates.map((d) => fmtDate(d)).join(" · ") })
              : t("title.notWatched")}
          </span>
        )}
        {ctl.canEdit && (
          <div className="manual-row">
            <WatchDateChips dates={dates} onRemove={(d) => ctl.removeEpisode(ep.id, d)} />
            <AddWatch onAdd={(date) => ctl.addEpisode(ep.id, date)}
              releaseDate={ep.air_date}
              label={ep.watched ? t("title.addWatch") : t("title.markWatched")} />
          </div>
        )}
      </div>
    </div>
  );
}

function Seasons({ seasons, ctl, live }: { seasons: any[]; ctl: Ctl; live?: Map<string, any> }) {
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
          <div style={{ marginTop: 10 }}>
            <TagChips tags={current.tags || []} canEdit={ctl.canEdit}
              attach={(tagId) => api.post(`/titles/${ctl.titleId}/seasons/${current.season}/tags/${tagId}`)}
              detach={(tagId) => api.del(`/titles/${ctl.titleId}/seasons/${current.season}/tags/${tagId}`)}
              onChange={ctl.reload} />
          </div>
        </div>
        <div className="episode-list">
          {current.episodes.map((ep: any) => (
            <EpisodeRow key={ep.id} ep={ep} ctl={ctl}
              live={live?.get(`${current.season}-${ep.episode}`)} />
          ))}
        </div>
      </div>
    </>
  );
}

// Manual title + poster override editor. Renaming a title or uploading a poster
// locks that field against TMDB/Trakt enrichment; "remove override" clears the
// lock and lets metadata take over again on the next open.
function TitleEditor({ ti, onDone }: { ti: any; onDone: () => void }) {
  const { toast } = useApp();
  const { t } = useT();
  const [title, setTitle] = useState<string>(ti.title || "");
  const [busy, setBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  async function run(fn: () => Promise<any>, ok: string) {
    setBusy(true);
    try {
      await fn();
      toast(ok, "ok");
      onDone();
    } catch (e) {
      toast(e instanceof ApiError ? e.message : t("settings.failed"), "err");
    } finally {
      setBusy(false);
    }
  }

  const saveTitle = () => {
    const v = title.trim();
    if (!v || v === ti.title) return;
    run(() => api.patch(`/titles/${ti.id}/rename`, { title: v }), t("title.edit.saved"));
  };
  const clearTitle = () =>
    run(() => api.del(`/titles/${ti.id}/rename`), t("title.edit.reverted"));
  const clearPoster = () =>
    run(() => api.del(`/titles/${ti.id}/poster`), t("title.edit.reverted"));
  const uploadPoster = (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    run(() => api.upload(`/titles/${ti.id}/poster`, fd), t("title.edit.saved"));
  };
  const toggleUnknown = () =>
    run(() => api.put(`/titles/${ti.id}/unknown`, { unknown: !ti.unknown }),
      !ti.unknown ? t("title.movedToUnknown", { title: ti.title }) : t("title.removedFromUnknown", { title: ti.title }));
  const setKind = (kind: string) => {
    if (kind === ti.kind) return;
    run(() => api.put(`/titles/${ti.id}/kind`, { kind }), t("title.edit.saved"));
  };
  const KINDS: { value: string; label: string }[] = [
    { value: "movie", label: t("common.film") },
    { value: "series", label: t("common.series") },
    { value: "tv", label: t("title.category.tv") },
  ];

  return (
    <div className="card" style={{ marginBottom: 20 }}>
      <div className="row" style={{ justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <strong>{t("title.edit.heading")}</strong>
        <button className="btn-ghost btn-sm" onClick={onDone} aria-label={t("common.close")}>
          <IconClose width={16} height={16} />
        </button>
      </div>

      <label className="caption" style={{ display: "block", marginBottom: 4 }}>{t("title.edit.titleLabel")}</label>
      <div className="row wrap" style={{ gap: 8, alignItems: "center", marginBottom: 16 }}>
        <input style={{ flex: 1, minWidth: 200 }} value={title} disabled={busy}
          onChange={(e) => setTitle(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") saveTitle(); }} />
        <button className="btn-primary btn-sm" disabled={busy || !title.trim() || title.trim() === ti.title}
          onClick={saveTitle}>{t("common.save")}</button>
        {ti.manual_title && (
          <button className="btn-ghost btn-sm" disabled={busy} onClick={clearTitle}>
            <IconRefresh width={15} height={15} /> {t("title.edit.removeOverride")}
          </button>
        )}
      </div>

      <label className="caption" style={{ display: "block", marginBottom: 4 }}>{t("title.edit.posterLabel")}</label>
      <div className="row wrap" style={{ gap: 8, alignItems: "center" }}>
        <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp" hidden
          onChange={(e) => { const f = e.target.files?.[0]; if (f) uploadPoster(f); e.target.value = ""; }} />
        <button className="btn-ghost btn-sm" disabled={busy} onClick={() => fileRef.current?.click()}>
          <IconPlus width={15} height={15} /> {ti.manual_poster ? t("title.edit.replacePoster") : t("title.edit.uploadPoster")}
        </button>
        {ti.manual_poster && (
          <button className="btn-ghost btn-sm" disabled={busy} onClick={clearPoster}>
            <IconRefresh width={15} height={15} /> {t("title.edit.removeOverride")}
          </button>
        )}
      </div>
      <label className="caption" style={{ display: "block", marginBottom: 4 }}>{t("title.edit.categoryLabel")}</label>
      <div className="row wrap" style={{ gap: 8, alignItems: "center", marginBottom: 16 }}>
        <div className="seg" role="group">
          {KINDS.map((k) => (
            <button key={k.value} className={ti.kind === k.value ? "active" : ""}
              disabled={busy} onClick={() => setKind(k.value)}>{k.label}</button>
          ))}
        </div>
      </div>

      <label className="caption" style={{ display: "block", marginBottom: 4 }}>{t("title.edit.unknownLabel")}</label>
      <div className="row wrap" style={{ gap: 8, alignItems: "center" }}>
        <button className="btn-ghost btn-sm" disabled={busy} onClick={toggleUnknown}>
          {ti.unknown ? t("title.removeFromUnknown") : t("title.moveToUnknown")}
        </button>
      </div>

      <p className="caption" style={{ marginTop: 10, marginBottom: 0 }}>{t("title.edit.hint")}</p>
    </div>
  );
}

export function TitleDetail() {
  const { id } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const { scope, can, toast, prefs } = useApp();
  const { t, lang } = useT();
  const tGenre = useGenre();
  const { data: ti, loading, error, reload, refresh } = useFetch<any>(
    () => api.get(`/search/title/${id}`, { profile: scope, lang }), [id, scope, lang]);
  const { data: providers } = useFetch<any[]>(() => api.get("/providers"), []);
  const [enriching, setEnriching] = useState(false);
  const [syncingTrakt, setSyncingTrakt] = useState(false);
  const [editing, setEditing] = useState(searchParams.get("edit") === "1");

  // Expert-mode progress layer: fetch this title's persistent progress. Unlike
  // now-playing, /scrobble/progress keeps returning the last known position
  // after playback stops, so a partly-watched film/episode shows where you left
  // off right on the title page.
  const { data: liveRaw, refresh: refreshLive } = useFetch<any[]>(
    () => (prefs.expert ? api.get("/scrobble/progress", { title_id: id }) : Promise.resolve([])),
    [prefs.expert, id]);
  useEffect(() => {
    if (!prefs.expert) return;
    const iv = setInterval(() => { refreshLive(); }, 5000);
    return () => clearInterval(iv);
  }, [prefs.expert, refreshLive]);

  // Opened from a long-press "Edit" action (?edit=1): consume the flag so a
  // reload or back-navigation doesn't force the editor open again.
  useEffect(() => {
    if (searchParams.get("edit") === "1") {
      const next = new URLSearchParams(searchParams);
      next.delete("edit");
      setSearchParams(next, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const canEdit = can("ingest.write");
  const targetBody = () => (scope && scope !== "all" ? { user_id: scope } : {});
  const scopeQ = () => (scope && scope !== "all" ? `&profile=${encodeURIComponent(scope)}` : "");

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

  async function setPlatform(providerId: string) {
    try {
      await api.put(`/titles/${id}/platform-override`, { provider_id: providerId || null });
      toast(t("title.platformUpdated"), "ok");
      reload();
    } catch (e) { toast(e instanceof ApiError ? e.message : t("settings.failed"), "err"); }
  }

  async function addTitleWatch(date: string) {
    try {
      await api.post(`/titles/${id}/watch`, { ...targetBody(), date });
      toast(t("title.watchAdded"), "ok");
      refresh();
    } catch (e) { toast(e instanceof ApiError ? e.message : t("settings.failed"), "err"); }
  }

  async function removeTitleWatch(date: string) {
    try {
      await api.del(`/titles/${id}/watch?date=${encodeURIComponent(date)}${scopeQ()}`);
      toast(t("title.watchRemoved"), "ok");
      refresh();
    } catch (e) { toast(e instanceof ApiError ? e.message : t("settings.failed"), "err"); }
  }

  const ctl: Ctl = {
    canEdit,
    titleId: id!,
    reload,
    addEpisode: async (episodeId, date) => {
      try {
        await api.post(`/episodes/${episodeId}/watch`, { ...targetBody(), date });
        toast(t("title.watchAdded"), "ok");
        refresh();
      } catch (e) { toast(e instanceof ApiError ? e.message : t("settings.failed"), "err"); }
    },
    addSeason: async (season, date) => {
      try {
        const res = await api.post(`/titles/${id}/seasons/${season}/watch`, { ...targetBody(), date });
        toast(t("title.seasonMarked", { n: res.inserted || 0 }), "ok");
        refresh();
      } catch (e) { toast(e instanceof ApiError ? e.message : t("settings.failed"), "err"); }
    },
    removeEpisode: async (episodeId, date) => {
      try {
        await api.del(`/episodes/${episodeId}/watch?date=${encodeURIComponent(date)}${scopeQ()}`);
        toast(t("title.watchRemoved"), "ok");
        refresh();
      } catch (e) { toast(e instanceof ApiError ? e.message : t("settings.failed"), "err"); }
    },
  };

  // Split live sessions for this title: a movie has at most one, a series keys
  // its live sessions by `season-episode` so each episode row can find its own.
  const liveForTitle = (liveRaw || []).filter((s: any) => s.title_id === id);
  const movieLive = ti.kind === "movie" ? liveForTitle[0] : undefined;
  const epLive = new Map<string, any>();
  if (ti.kind === "series") {
    for (const s of liveForTitle) {
      if (s.season != null && s.episode != null) epLive.set(`${s.season}-${s.episode}`, s);
    }
  }

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
            <div className="row" style={{ gap: 10, alignItems: "center" }}>
              <h1 className="large-title" style={{ margin: 0 }}>{ti.title}</h1>
              {canEdit && (
                <button className="btn-ghost btn-sm" title={t("title.edit.heading")}
                  aria-label={t("title.edit.heading")} onClick={() => setEditing((v) => !v)}>
                  <IconPencil width={16} height={16} />
                </button>
              )}
              {(ti.manual_title || ti.manual_poster) && (
                <span className="chip" style={{ minHeight: 0, padding: "2px 10px" }}>{t("title.edit.badge")}</span>
              )}
            </div>
            <div className="row wrap" style={{ gap: 8 }}>
              <span className="chip" style={{ minHeight: 0, padding: "2px 10px" }}>{mediaBadge(t, ti)}</span>
              {ti.year && <span className="chip" style={{ minHeight: 0, padding: "2px 10px" }}>{ti.year}</span>}
              {ti.runtime_minutes && <span className="chip" style={{ minHeight: 0, padding: "2px 10px" }}>{t("title.min", { n: ti.runtime_minutes })}</span>}
            </div>
            <div className="chips">{ti.genres?.map((g: string) => (
              <Link key={g} to={`/search?genre=${encodeURIComponent(g)}&kind=${ti.kind}`} className="chip"
                style={{ color: "inherit", textDecoration: "none" }}>{tGenre(g)}</Link>
            ))}</div>
            {ti.networks?.length > 0 && (
              <div className="chips" style={{ alignItems: "center" }}>
                <span className="caption" style={{ marginRight: 2 }}>{t("title.network")}:</span>
                {ti.networks.map((n: any, i: number) => (
                  <NetworkLogo key={i} logo={n.logo} name={n.name} />
                ))}
              </div>
            )}
            <TagChips tags={ti.tags || []} canEdit={canEdit}
              attach={(tagId) => api.post(`/titles/${id}/tags/${tagId}`)}
              detach={(tagId) => api.del(`/titles/${id}/tags/${tagId}`)}
              onChange={reload} />
          </div>
        </div>
      </div>

      {canEdit && editing && (
        <TitleEditor ti={ti} onDone={() => { setEditing(false); reload(); }} />
      )}

      {ti.overview && <p className="muted" style={{ margin: "20px 0" }}>{ti.overview}</p>}

      {/* Live now-playing for a movie: real-time progress mirrored from the
          dashboard, shown right on the title it belongs to (Expert mode). */}
      {movieLive && <LiveNowBar live={movieLive} />}

      {canEdit && (
        <div className="row wrap" style={{ gap: 10, marginBottom: 20, alignItems: "center" }}>
          <button className="btn-ghost btn-sm" disabled={enriching} onClick={enrich}>
            <IconSparkles width={16} height={16} /> {enriching ? t("title.enriching") : t("title.enrichTmdb")}
          </button>
          {ti.trakt_configured && (
            <button className="btn-ghost btn-sm" disabled={syncingTrakt} onClick={syncTrakt}>
              <IconRefresh width={16} height={16} /> {syncingTrakt ? t("title.syncingTrakt") : t("title.syncTrakt")}
            </button>
          )}
          <div className="spacer" style={{ flex: 1 }} />
          {(() => {
            const pd = platformDropdown(providers || [], ti.kind, ti.platform_override?.id || "");
            return <PlatformSelect value={pd.value} providers={pd.options} onChange={setPlatform} />;
          })()}
        </div>
      )}

      {/* Watch dates for a movie (series mark/remove per season/episode). */}
      {canEdit && ti.kind === "movie" && (
        <div className="card" style={{ marginBottom: 20 }}>
          <div className="row wrap" style={{ gap: 12, alignItems: "center" }}>
            <strong>{t("title.watchDates")}</strong>
            <WatchDateChips dates={ti.watch_dates || []} onRemove={removeTitleWatch} />
            <div className="spacer" style={{ flex: 1 }} />
            <AddWatch onAdd={addTitleWatch} releaseDate={ti.release_date}
              label={ti.watch_dates?.length ? t("title.addWatch") : t("title.markWatched")} />
          </div>
        </div>
      )}

      {ti.kind === "tv" && (
        <div className="card" style={{ marginBottom: 20 }}>
          <div className="row wrap" style={{ gap: 24, alignItems: "center" }}>
            <div className="col" style={{ gap: 2 }}>
              <strong style={{ fontSize: 22 }}>{fmtNum(ti.tv_watch_count || 0)}×</strong>
              <span className="caption">{t("title.tv.watchCount")}</span>
            </div>
            <div className="col" style={{ gap: 2 }}>
              <strong style={{ fontSize: 22 }}>{fmtDurationHM(t, ti.tv_total_seconds || 0)}</strong>
              <span className="caption">{t("title.tv.totalTime")}</span>
            </div>
          </div>
        </div>
      )}

      {ti.kind === "series" && ti.seasons?.length > 0 && <Seasons seasons={ti.seasons} ctl={ctl} live={epLive} />}

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
                  <span className="caption">{providerLabel(t, e.platform_key, e.platform)} · {e.who}</span>
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
