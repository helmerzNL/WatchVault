import { useEffect, useState, useCallback } from "react";
import { useApp } from "../lib/app";
import { useT } from "../lib/i18n";
import { api, ApiError } from "../lib/api";
import { IconClose } from "./icons";

interface Ep { episode: number; name: string | null; }
interface Season { season: number; episodes: Ep[]; episode_count: number; }
interface SeasonsResp {
  title_id?: string;
  current?: { season: number | null; episode: number | null } | null;
  seasons: Season[];
  backfilling?: boolean;
  reason?: string;
}

// Long-press picker for a live SkyShowtime/Videoland session: lets the viewer
// bind the currently-playing show to a concrete season+episode (TMDB-driven).
export function EpisodePicker({ session, onClose, onSaved }: {
  session: any; onClose: () => void; onSaved: () => void;
}) {
  const { t } = useT();
  const { toast } = useApp();
  const [data, setData] = useState<SeasonsResp | null>(null);
  const [err, setErr] = useState(false);
  const [selSeason, setSelSeason] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setErr(false); setData(null);
    try {
      const res: SeasonsResp = await api.get(`/scrobble/sessions/${session.id}/seasons`);
      setData(res);
      const cur = res.current?.season;
      const first = res.seasons[0]?.season ?? null;
      setSelSeason(cur != null && res.seasons.some(s => s.season === cur) ? cur : first);
    } catch {
      setErr(true);
    }
  }, [session.id]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  async function pick(season: number, episode: number) {
    if (saving) return;
    setSaving(true);
    try {
      await api.post(`/scrobble/sessions/${session.id}/episode`, { season, episode });
      toast(t("scrobble.pickSaved"), "ok");
      onSaved();
      onClose();
    } catch (e) {
      toast(e instanceof ApiError ? e.message : t("scrobble.pickFailed"), "err");
      setSaving(false);
    }
  }

  const seasons = data?.seasons ?? [];
  const active = seasons.find(s => s.season === selSeason) ?? null;
  const curSeason = data?.current?.season ?? null;
  const curEpisode = data?.current?.episode ?? null;

  return (
    <div className="cinema-scrim" onMouseDown={onClose}>
      <div className="cinema-dialog card glass" onMouseDown={(e) => e.stopPropagation()}>
        <div className="row" style={{ marginBottom: 6 }}>
          <strong style={{ fontSize: 17 }}>{t("scrobble.pickTitle")}</strong>
          <div className="spacer" style={{ flex: 1 }} />
          <button className="btn-ghost btn-sm" onClick={onClose} aria-label={t("common.cancel")}>
            <IconClose width={18} height={18} />
          </button>
        </div>
        <div className="caption muted" style={{ marginBottom: 14, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
          {session.title}
        </div>

        {err ? (
          <div className="col" style={{ gap: 12 }}>
            <p className="muted">{t("scrobble.pickFailed")}</p>
            <button className="btn-ghost btn-sm" onClick={load}>{t("scrobble.pickRetry")}</button>
          </div>
        ) : data === null ? (
          <p className="muted">{t("scrobble.pickLoading")}</p>
        ) : data.backfilling ? (
          <div className="col" style={{ gap: 12 }}>
            <p className="muted">{t("scrobble.pickBackfilling")}</p>
            <button className="btn-ghost btn-sm" onClick={load}>{t("scrobble.pickRetry")}</button>
          </div>
        ) : seasons.length === 0 ? (
          <p className="muted">{t("scrobble.pickNone")}</p>
        ) : (
          <>
            <div className="row wrap" style={{ gap: 6, marginBottom: 14 }}>
              {seasons.map(s => (
                <button key={s.season}
                  className={`chip ${s.season === selSeason ? "active" : ""}`}
                  style={{ minHeight: 0, padding: "4px 12px" }}
                  onClick={() => setSelSeason(s.season)}>
                  {t("scrobble.pickSeasonN", { n: s.season })}
                </button>
              ))}
            </div>
            <div className="cinema-results">
              {(active?.episodes ?? []).map(ep => {
                const isCur = active!.season === curSeason && ep.episode === curEpisode;
                return (
                  <button key={ep.episode}
                    className={`cinema-hit ${isCur ? "selected" : ""}`}
                    disabled={saving}
                    onClick={() => pick(active!.season, ep.episode)}>
                    <div className="cinema-hit-meta">
                      <div className="t">
                        {t("scrobble.pickEpisodeN", { n: ep.episode })}
                        {ep.name ? ` · ${ep.name}` : ""}
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
