import { useParams, Link } from "react-router-dom";
import { useApp } from "../lib/app";
import { useT } from "../lib/i18n";
import { api } from "../lib/api";
import { useFetch } from "../lib/useFetch";
import { Loading, ErrorState, Poster } from "../components/ui";
import { IconChevron } from "../components/icons";
import { fmtDate } from "../lib/format";

export function Person() {
  const { id } = useParams();
  const { t, lang } = useT();
  const { data: p, loading, error, reload } = useFetch<any>(
    () => api.get(`/people/${id}`, { lang }), [id, lang]);

  if (loading) return <Loading label={t("person.loading")} />;
  if (error) return <ErrorState error={error} retry={reload} />;
  if (!p) return null;

  const meta: string[] = [];
  if (p.birthday) meta.push(`${t("person.born")} ${fmtDate(p.birthday)}`);
  if (p.deathday) meta.push(`${t("person.died")} ${fmtDate(p.deathday)}`);
  if (p.place_of_birth) meta.push(p.place_of_birth);

  return (
    <>
      <Link to="/search" className="btn-ghost btn-sm" style={{ marginBottom: 16 }}>
        <IconChevron width={16} height={16} style={{ transform: "rotate(180deg)" }} /> {t("common.back")}
      </Link>

      <div className="card">
        <div className="row" style={{ gap: 20, alignItems: "flex-start" }}>
          <span className="avatar" style={{ width: 96, height: 96, flexShrink: 0, fontSize: 28 }}>
            {p.photo ? <img src={p.photo} alt={p.name} /> : (p.name?.[0] || "?")}
          </span>
          <div className="col" style={{ gap: 6, flex: 1 }}>
            <h1 className="large-title">{p.name}</h1>
            {meta.length > 0 && <span className="caption">{meta.join(" · ")}</span>}
            {p.known_for && <span className="caption">{t("person.knownFor")}: {p.known_for}</span>}
          </div>
        </div>
      </div>

      <h2 className="title" style={{ margin: "24px 0 12px" }}>{t("person.biography")}</h2>
      <p className="muted" style={{ whiteSpace: "pre-line" }}>
        {p.biography || t("person.noBio")}
      </p>

      <h2 className="title" style={{ margin: "28px 0 14px" }}>{t("person.appearsIn")}</h2>
      {p.titles?.length ? (
        <div className="poster-grid">
          {p.titles.map((tt: any) => (
            <Poster key={tt.id} to={`/title/${tt.id}`} poster={tt.poster} title={tt.title} kind={tt.kind}
              subtitle={[tt.role, tt.year].filter(Boolean).join(" · ")}
              badge={tt.kind === "movie" ? t("common.film") : t("common.series")} />
          ))}
        </div>
      ) : <p className="muted">{t("person.noTitles")}</p>}
    </>
  );
}
