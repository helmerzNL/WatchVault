import type { ReactNode } from "react";
import { useEffect, useRef } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ApiError } from "../lib/api";
import { useT } from "../lib/i18n";
import { enqueueEnrich } from "../lib/lazyEnrich";
import { monthKey, monthLabel } from "../lib/format";
import { IconFilm, IconTv, IconChevron } from "./icons";

export function Loading({ label }: { label?: string }) {
  const { t } = useT();
  return (
    <div className="loading-box">
      <div className="spinner" />
      <div className="muted">{label ?? t("common.loading")}</div>
    </div>
  );
}

export function BackLink({ to = "/search", label }: { to?: string; label?: string }) {
  const { t } = useT();
  const navigate = useNavigate();
  // React Router records a history index; >0 means there's an in-app screen to
  // return to. Otherwise (direct deep-link / fresh tab) fall back to `to`.
  const canGoBack = typeof window !== "undefined" && ((window.history.state?.idx ?? 0) > 0);
  const inner = (
    <>
      <IconChevron width={18} height={18} style={{ transform: "rotate(180deg)" }} />
      <span>{label ?? t("common.back")}</span>
    </>
  );
  if (canGoBack) {
    return (
      <button type="button" className="btn-back" onClick={() => navigate(-1)}>
        {inner}
      </button>
    );
  }
  return (
    <Link to={to} className="btn-back">
      {inner}
    </Link>
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
  const { t } = useT();
  const msg = error instanceof ApiError ? error.message : error instanceof Error ? error.message : String(error);
  return (
    <div className="empty">
      <div className="title" style={{ marginBottom: 8 }}>{t("common.somethingWrong")}</div>
      <p className="muted" style={{ marginBottom: 16 }}>{msg}</p>
      {retry && <button className="btn-ghost" onClick={retry}>{t("common.tryAgain")}</button>}
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

// Segmented toggle, shared by the overview filters and the dashboard.
export function Seg<T extends string>({ value, onChange, options }: {
  value: T; onChange: (v: T) => void; options: { value: T; label: string }[];
}) {
  return (
    <div className="seg">
      {options.map((o) => (
        <button key={o.value} className={value === o.value ? "active" : ""} onClick={() => onChange(o.value)}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

export type Range = "all" | "week" | "month" | "year";

// Time-range filter (Alles / Week / Maand / Jaar) reused across breakdowns.
export function RangeSeg({ value, onChange }: { value: Range; onChange: (v: Range) => void }) {
  const { t } = useT();
  return (
    <Seg<Range> value={value} onChange={onChange} options={[
      { value: "all", label: t("common.all") },
      { value: "week", label: t("overviews.week") },
      { value: "month", label: t("overviews.month") },
      { value: "year", label: t("overviews.year") },
    ]} />
  );
}

// Previous/next month navigator (YYYY-MM). The "next" button is disabled once
// at the current month so you can't page into the future. Uses local-tz labels.
export function MonthNav({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const { t } = useT();
  const shift = (delta: number) => {
    const [y, m] = value.split("-").map(Number);
    onChange(monthKey(new Date(y, m - 1 + delta, 1)));
  };
  const atCurrent = value >= monthKey(new Date());
  return (
    <div className="month-nav">
      <button type="button" className="month-nav-btn" onClick={() => shift(-1)}
        aria-label={t("common.prevMonth")}>
        <IconChevron width={16} height={16} style={{ transform: "rotate(180deg)" }} />
      </button>
      <span className="month-nav-label">{monthLabel(value)}</span>
      <button type="button" className="month-nav-btn" onClick={() => shift(1)} disabled={atCurrent}
        aria-label={t("common.nextMonth")}>
        <IconChevron width={16} height={16} />
      </button>
    </div>
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
  poster, title, subtitle, badge, kind, to, enrichId,
}: {
  poster?: string | null;
  title: string;
  subtitle?: string;
  badge?: string;
  kind?: string;
  to?: string;
  enrichId?: string | null;
}) {
  const ref = useRef<HTMLAnchorElement | HTMLDivElement | null>(null);

  useEffect(() => {
    if (!enrichId || !ref.current || typeof IntersectionObserver === "undefined") return;
    const el = ref.current;
    const obs = new IntersectionObserver((entries) => {
      for (const e of entries) {
        if (e.isIntersecting) { enqueueEnrich(enrichId); obs.disconnect(); break; }
      }
    }, { rootMargin: "200px" });
    obs.observe(el);
    return () => obs.disconnect();
  }, [enrichId]);

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
  return to
    ? <Link ref={ref as any} to={to} className="poster-tile">{inner}</Link>
    : <div ref={ref as any} className="poster-tile">{inner}</div>;
}
