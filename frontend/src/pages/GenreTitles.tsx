import { useParams } from "react-router-dom";
import { useApp } from "../lib/app";
import { useT, useGenre, mediaBadge } from "../lib/i18n";
import { api } from "../lib/api";
import { useFetch } from "../lib/useFetch";
import { Loading, ErrorState, Poster, BackLink } from "../components/ui";
import { fmtHours } from "../lib/format";

export function GenreTitles() {
  const { id } = useParams();
  const { scope } = useApp();
  const { t } = useT();
  const tGenre = useGenre();
  const { data, loading, error, reload } = useFetch<any>(
    () => api.get("/stats/genre-titles", { profile: scope, genre: id }), [id, scope]);

  if (loading) return <Loading />;
  if (error) return <ErrorState error={error} retry={reload} />;

  const titles = data?.titles || [];
  const heading = data?.genre ? t("genre.titlesIn", { genre: tGenre(data.genre) }) : "";

  return (
    <>
      <BackLink to="/overviews" />
      <h1 className="large-title" style={{ margin: "8px 0 16px" }}>{heading}</h1>
      {titles.length ? (
        <div className="poster-grid">
          {titles.map((m: any) => (
            <Poster key={m.id} to={`/title/${m.id}`} poster={m.poster} title={m.title} kind={m.kind}
              enrichId={m.id}
              subtitle={m.kind === "movie" ? `${m.year || ""}` : `${m.episodes} ep · ${fmtHours(m.hours)}`}
              badge={mediaBadge(t, m)} />
          ))}
        </div>
      ) : <p className="muted">{t("genre.empty")}</p>}
    </>
  );
}
