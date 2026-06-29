import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { ApiError } from "../lib/api";
import { IconFilm, IconTv } from "./icons";

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="loading-box">
      <div className="spinner" />
      <div className="muted">{label}</div>
    </div>
  );
}

export function Empty({ title, hint, action }: { title: string; hint?: string; action?: ReactNode }) {
  return (
    <div className="empty">
      <div className="title" style={{ marginBottom: 8 }}>{title}</div>
      {hint && <p className="muted" style={{ maxWidth: 420, margin: "0 auto 16px" }}>{hint}</p>}
      {action}
    </div>
  );
}

export function ErrorState({ error, retry }: { error: unknown; retry?: () => void }) {
  const msg = error instanceof ApiError ? error.message : error instanceof Error ? error.message : String(error);
  return (
    <div className="empty">
      <div className="title" style={{ marginBottom: 8 }}>Something went wrong</div>
      <p className="muted" style={{ marginBottom: 16 }}>{msg}</p>
      {retry && <button className="btn-ghost" onClick={retry}>Try again</button>}
    </div>
  );
}

export function Section({ title, right, children }: { title: string; right?: ReactNode; children?: ReactNode }) {
  return (
    <>
      <div className="section-head">
        <h2 className="title">{title}</h2>
        <div className="spacer" />
        {right}
      </div>
      {children}
    </>
  );
}

export function Stat({ value, label }: { value: ReactNode; label: string }) {
  return (
    <div className="card stat">
      <div className="value">{value}</div>
      <div className="key">{label}</div>
    </div>
  );
}

export function Poster({
  poster, title, subtitle, badge, kind, to,
}: {
  poster?: string | null;
  title: string;
  subtitle?: string;
  badge?: string;
  kind?: string;
  to?: string;
}) {
  const inner = (
    <>
      <div className="poster">
        {poster ? (
          <img src={poster} alt={title} loading="lazy" />
        ) : (
          <div className="ph">
            {kind === "movie" ? <IconFilm width={28} height={28} /> : <IconTv width={28} height={28} />}
            <span style={{ display: "block", marginTop: 6 }}>{title}</span>
          </div>
        )}
        {badge && <span className="badge">{badge}</span>}
      </div>
      <div className="poster-cap">
        <div className="t">{title}</div>
        {subtitle && <div className="s">{subtitle}</div>}
      </div>
    </>
  );
  return to ? <Link to={to} className="poster-tile">{inner}</Link> : <div className="poster-tile">{inner}</div>;
}
