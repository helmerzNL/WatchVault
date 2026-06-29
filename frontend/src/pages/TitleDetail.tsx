import { useParams, Link } from "react-router-dom";
import { useApp } from "../lib/app";
import { api, ApiError } from "../lib/api";
import { useFetch } from "../lib/useFetch";
import { Loading, ErrorState } from "../components/ui";
import { IconSparkles, IconChevron } from "../components/icons";
import { fmtDate } from "../lib/format";
import { useState } from "react";

export function TitleDetail() {
  const { id } = useParams();
  const { scope, can, toast } = useApp();
  const { data: t, loading, error, reload } = useFetch<any>(
    () => api.get(`/search/title/${id}`, { profile: scope }), [id, scope]);
  const [enriching, setEnriching] = useState(false);

  if (loading) return <Loading />;
  if (error) return <ErrorState error={error} retry={reload} />;
  if (!t) return null;

  async function enrich() {
    setEnriching(true);
    try {
      const res = await api.post(`/titles/${id}/enrich`);
      const ok = res.status === "enriched";
      toast(ok ? "Enriched with TMDB" : `Couldn't enrich (${res.status || "no match"})`, ok ? "ok" : "err");
      reload();
    } catch (e) { toast(e instanceof ApiError ? e.message : "Failed", "err"); }
    finally { setEnriching(false); }
  }

  return (
    <>
      <Link to="/search" className="btn-ghost btn-sm" style={{ marginBottom: 16 }}>
        <IconChevron width={16} height={16} style={{ transform: "rotate(180deg)" }} /> Back
      </Link>

      <div className="title-hero card" style={t.backdrop ? {
        backgroundImage: `linear-gradient(to top, var(--bg-elev), rgba(0,0,0,0.1)), url(${t.backdrop})`,
        backgroundSize: "cover", backgroundPosition: "center",
      } : undefined}>
        <div className="row" style={{ gap: 20, alignItems: "flex-end" }}>
          <div className="poster" style={{ width: 130, flexShrink: 0 }}>
            {t.poster ? <img src={t.poster} alt={t.title} /> : <div className="ph">{t.title}</div>}
          </div>
          <div className="col" style={{ gap: 8 }}>
            <h1 className="large-title">{t.title}</h1>
            <div className="row wrap" style={{ gap: 8 }}>
              <span className="chip" style={{ minHeight: 0, padding: "2px 10px" }}>{t.kind === "movie" ? "Film" : "Series"}</span>
              {t.year && <span className="chip" style={{ minHeight: 0, padding: "2px 10px" }}>{t.year}</span>}
              {t.runtime_minutes && <span className="chip" style={{ minHeight: 0, padding: "2px 10px" }}>{t.runtime_minutes} min</span>}
            </div>
            <div className="chips">{t.genres?.map((g: string) => <span key={g} className="chip">{g}</span>)}</div>
          </div>
        </div>
      </div>

      {t.overview && <p className="muted" style={{ margin: "20px 0" }}>{t.overview}</p>}

      {can("ingest.write") && (
        <button className="btn-ghost btn-sm" disabled={enriching} onClick={enrich} style={{ marginBottom: 20 }}>
          <IconSparkles width={16} height={16} /> {enriching ? "Enriching…" : "Enrich with TMDB"}
        </button>
      )}

      {t.cast?.length > 0 && (
        <>
          <h2 className="title" style={{ margin: "8px 0 14px" }}>Cast</h2>
          <div className="cast-row">
            {t.cast.map((c: any, i: number) => (
              <div key={i} className="cast-card">
                <span className="avatar" style={{ width: 56, height: 56 }}>
                  {c.profile ? <img src={c.profile} alt="" /> : (c.name?.[0] || "?")}
                </span>
                <span className="caption" style={{ fontWeight: 600, color: "var(--text)" }}>{c.name}</span>
                {c.character && <span className="caption">{c.character}</span>}
              </div>
            ))}
          </div>
        </>
      )}

      <h2 className="title" style={{ margin: "28px 0 14px" }}>Watch history</h2>
      <div className="card">
        {t.events?.length ? t.events.map((e: any, i: number) => (
          <div key={i} className="list-row">
            <div className="col" style={{ flex: 1, gap: 2 }}>
              <strong>
                {e.kind === "episode" && e.season != null
                  ? `S${e.season}${e.episode != null ? `E${e.episode}` : ""}${e.raw_title ? " · " + e.raw_title : ""}`
                  : e.raw_title || t.title}
              </strong>
              <span className="caption">{e.platform} · {e.who}</span>
            </div>
            <span className="caption">{fmtDate(e.date)}</span>
          </div>
        )) : <p className="muted">No watch events for this profile.</p>}
      </div>
    </>
  );
}
