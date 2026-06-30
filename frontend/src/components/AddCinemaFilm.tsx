import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useApp } from "../lib/app";
import { useT } from "../lib/i18n";
import { api, ApiError } from "../lib/api";
import { todayLocalKey, localDateKey, fmtDate } from "../lib/format";
import { IconPlus, IconClose, IconSearch, IconFilm } from "./icons";

interface Hit {
  tmdb_id: number;
  title: string;
  year: number | null;
  release_date: string | null;
  poster: string | null;
  overview: string | null;
}

const yesterdayKey = () => {
  const d = new Date();
  d.setDate(d.getDate() - 1);
  return localDateKey(d);
};

// Entry-point button. Lives on Search, Dashboard and (under Expert) Settings.
// `variant` only tweaks styling so it fits each surface; the modal is shared.
export function AddCinemaFilmButton({ variant = "primary" }: { variant?: "primary" | "ghost" | "block" }) {
  const { t } = useT();
  const { prefs } = useApp();
  const [open, setOpen] = useState(false);
  if (prefs.cinemaAdd === false) return null;
  const cls = variant === "primary" ? "btn-primary" : variant === "block" ? "btn" : "btn-ghost";
  return (
    <>
      <button className={`${cls} row`} style={{ gap: 8 }} onClick={() => setOpen(true)}>
        <IconPlus width={18} height={18} />
        {t("cinema.add")}
      </button>
      {open && <AddCinemaFilmModal onClose={() => setOpen(false)} />}
    </>
  );
}

function AddCinemaFilmModal({ onClose }: { onClose: () => void }) {
  const { t } = useT();
  const { toast } = useApp();
  const navigate = useNavigate();

  const [q, setQ] = useState("");
  const [results, setResults] = useState<Hit[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [picked, setPicked] = useState<Hit | null>(null);
  const [date, setDate] = useState(todayLocalKey);
  const [busy, setBusy] = useState(false);
  const reqRef = useRef(0);
  const td = todayLocalKey();

  // Close on Escape.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  // Debounced TMDB search (only the public query is sent to TMDB).
  useEffect(() => {
    const term = q.trim();
    if (!term) { setResults(null); return; }
    const id = ++reqRef.current;
    const handle = setTimeout(async () => {
      setSearching(true);
      try {
        const res = await api.get("/catalog/tmdb-search", { q: term });
        if (reqRef.current === id) setResults(res.results || []);
      } catch {
        if (reqRef.current === id) setResults([]);
      } finally {
        if (reqRef.current === id) setSearching(false);
      }
    }, 320);
    return () => clearTimeout(handle);
  }, [q]);

  async function submit() {
    if (!picked || busy) return;
    setBusy(true);
    try {
      const res = await api.post("/catalog/add-film", {
        tmdb_id: picked.tmdb_id, title: picked.title, year: picked.year, date,
      });
      toast(t("cinema.added", { title: res.title || picked.title }), "ok");
      onClose();
      navigate(`/title/${res.title_id}`);
    } catch (e) {
      toast(e instanceof ApiError ? e.message : t("cinema.failed"), "err");
    } finally {
      setBusy(false);
    }
  }

  const release = picked?.release_date && picked.release_date.length >= 10
    ? picked.release_date.slice(0, 10) : null;

  return (
    <div className="cinema-scrim" onMouseDown={onClose}>
      <div className="cinema-dialog card glass" onMouseDown={(e) => e.stopPropagation()}>
        <div className="row" style={{ marginBottom: 14 }}>
          <strong style={{ fontSize: 17 }}>{t("cinema.dialogTitle")}</strong>
          <div className="spacer" style={{ flex: 1 }} />
          <button className="btn-ghost btn-sm" onClick={onClose} aria-label={t("common.cancel")}>
            <IconClose width={18} height={18} />
          </button>
        </div>

        {!picked ? (
          <>
            <div className="row" style={{ gap: 10, marginBottom: 14 }}>
              <IconSearch width={20} height={20} className="muted" />
              <input value={q} onChange={(e) => setQ(e.target.value)} autoFocus
                placeholder={t("cinema.searchPlaceholder")}
                style={{ border: "none", minHeight: 32, padding: 0, background: "transparent", flex: 1 }} />
            </div>
            <div className="cinema-results">
              {searching && results === null ? (
                <p className="muted">{t("cinema.searching")}</p>
              ) : results === null ? (
                <p className="muted">{t("cinema.searchHint")}</p>
              ) : results.length === 0 ? (
                <p className="muted">{t("cinema.noResults")}</p>
              ) : (
                results.map((r) => (
                  <button key={r.tmdb_id} className="cinema-hit" onClick={() => setPicked(r)}>
                    <div className="cinema-hit-poster">
                      {r.poster ? <img src={r.poster} alt={r.title} loading="lazy" />
                        : <div className="ph"><IconFilm width={22} height={22} /></div>}
                    </div>
                    <div className="cinema-hit-meta">
                      <div className="t">{r.title}</div>
                      {r.year && <div className="s muted">{r.year}</div>}
                      {r.release_date && <div className="d tertiary">{fmtDate(r.release_date)}</div>}
                    </div>
                  </button>
                ))
              )}
            </div>
          </>
        ) : (
          <>
            <button className="cinema-hit selected" onClick={() => setPicked(null)}>
              <div className="cinema-hit-poster">
                {picked.poster ? <img src={picked.poster} alt={picked.title} />
                  : <div className="ph"><IconFilm width={22} height={22} /></div>}
              </div>
              <div className="cinema-hit-meta">
                <div className="t">{picked.title}</div>
                {picked.year && <div className="s muted">{picked.year}</div>}
                {picked.release_date && <div className="d tertiary">{fmtDate(picked.release_date)}</div>}
              </div>
            </button>

            <label style={{ display: "block", margin: "16px 0 8px" }}>{t("cinema.watchedOn")}</label>
            <div className="row wrap" style={{ gap: 6, marginBottom: 10 }}>
              {release && release <= td && (
                <button className={`chip ${date === release ? "active" : ""}`} style={{ minHeight: 0, padding: "4px 10px" }}
                  onClick={() => setDate(release)}>{t("title.releaseDate")}</button>
              )}
              <button className={`chip ${date === yesterdayKey() ? "active" : ""}`} style={{ minHeight: 0, padding: "4px 10px" }}
                onClick={() => setDate(yesterdayKey())}>{t("common.yesterday")}</button>
              <button className={`chip ${date === td ? "active" : ""}`} style={{ minHeight: 0, padding: "4px 10px" }}
                onClick={() => setDate(td)}>{t("common.today")}</button>
            </div>
            <input type="date" value={date} max={td}
              onChange={(e) => e.target.value && setDate(e.target.value)} style={{ marginBottom: 18 }} />

            <div className="row" style={{ gap: 8, justifyContent: "flex-end" }}>
              <button className="btn-ghost" onClick={() => setPicked(null)} disabled={busy}>{t("common.back")}</button>
              <button className="btn-primary" onClick={submit} disabled={busy}>
                {busy ? t("cinema.adding") : t("cinema.add")}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

