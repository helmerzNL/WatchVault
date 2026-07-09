import type { ReactNode } from "react";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, ApiError } from "../lib/api";
import { useApp } from "../lib/app";
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

export function Section({ title, right, children, bare }: { title: string; right?: ReactNode; children?: ReactNode; bare?: boolean }) {
  return (
    <>
      {!bare && (
      <div className="section-head">
        <h2 className="title">{title}</h2>
        <div className="spacer" />
        {right}
      </div>
      )}
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
  poster, title, subtitle, badge, kind, to, enrichId, titleId,
}: {
  poster?: string | null;
  title: string;
  subtitle?: string;
  badge?: string;
  kind?: string;
  to?: string;
  enrichId?: string | null;
  titleId?: string | null;
}) {
  const ref = useRef<HTMLAnchorElement | HTMLDivElement | null>(null);
  const { t } = useT();
  const { prefs, toast } = useApp();

  // The title id is needed to delete; prefer an explicit prop, fall back to the
  // enrich id (same value at every grid callsite) or parse it out of `to`.
  const delId =
    titleId ?? enrichId ??
    (to ? to.match(/^\/title\/([^/?#]+)/)?.[1] ?? null : null);
  const canDelete = !!(prefs.expert && delId);

  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [deleted, setDeleted] = useState(false);
  const pressTimer = useRef<number | null>(null);
  const longPressed = useRef(false);
  const startPt = useRef<{ x: number; y: number } | null>(null);

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

  useEffect(() => () => {
    if (pressTimer.current) window.clearTimeout(pressTimer.current);
  }, []);

  const clearTimer = () => {
    if (pressTimer.current) { window.clearTimeout(pressTimer.current); pressTimer.current = null; }
  };

  // Long-press (touch or mouse-hold) opens the delete confirmation. Movement or
  // an early release cancels it so scrolling never triggers a delete.
  const onPointerDown = (e: React.PointerEvent) => {
    if (!canDelete || e.button === 2) return;
    longPressed.current = false;
    startPt.current = { x: e.clientX, y: e.clientY };
    clearTimer();
    pressTimer.current = window.setTimeout(() => {
      longPressed.current = true;
      setConfirm(true);
    }, 550);
  };
  const onPointerMove = (e: React.PointerEvent) => {
    if (!pressTimer.current || !startPt.current) return;
    if (Math.abs(e.clientX - startPt.current.x) > 10 ||
        Math.abs(e.clientY - startPt.current.y) > 10) clearTimer();
  };
  const onClickCapture = (e: React.MouseEvent) => {
    // Suppress the navigation that a long-press would otherwise trigger.
    if (longPressed.current) { e.preventDefault(); e.stopPropagation(); longPressed.current = false; }
  };
  const onContextMenu = (e: React.MouseEvent) => {
    if (!canDelete) return;
    e.preventDefault();
    setConfirm(true);
  };

  const doDelete = async () => {
    if (!delId) return;
    setBusy(true);
    try {
      await api.del(`/titles/${delId}`);
      setConfirm(false);
      setDeleted(true);
      toast(t("title.deleted", { title }), "ok");
      window.dispatchEvent(new CustomEvent("watchvault:title-deleted", { detail: delId }));
    } catch (err) {
      toast(err instanceof ApiError ? err.message : t("title.deleteFailed"), "err");
    } finally {
      setBusy(false);
    }
  };

  if (deleted) return null;

  const pressHandlers = canDelete ? {
    onPointerDown, onPointerMove,
    onPointerUp: clearTimer, onPointerCancel: clearTimer, onPointerLeave: clearTimer,
    onClickCapture, onContextMenu,
  } : {};

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

  const tile = to
    ? <Link ref={ref as any} to={to} className="poster-tile" {...pressHandlers}>{inner}</Link>
    : <div ref={ref as any} className="poster-tile" {...pressHandlers}>{inner}</div>;

  return (
    <>
      {tile}
      {confirm && (
        <DeleteTitleConfirm
          title={title}
          busy={busy}
          onCancel={() => { if (!busy) setConfirm(false); }}
          onConfirm={doDelete}
        />
      )}
    </>
  );
}

function DeleteTitleConfirm({
  title, busy, onCancel, onConfirm,
}: { title: string; busy: boolean; onCancel: () => void; onConfirm: () => void }) {
  const { t } = useT();
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onCancel(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onCancel]);
  return (
    <div className="cinema-scrim" onMouseDown={onCancel}>
      <div className="cinema-dialog card glass" onMouseDown={(e) => e.stopPropagation()}
        style={{ maxWidth: 380 }}>
        <strong style={{ fontSize: 17 }}>{t("title.deleteTitle")}</strong>
        <p className="muted" style={{ margin: "12px 0 18px" }}>
          {t("title.deleteConfirm", { title })}
        </p>
        <div className="row" style={{ gap: 10, justifyContent: "flex-end" }}>
          <button className="btn-ghost" onClick={onCancel} disabled={busy}>
            {t("common.cancel")}
          </button>
          <button className="btn-danger" onClick={onConfirm} disabled={busy}>
            {busy ? t("title.deleting") : t("title.delete")}
          </button>
        </div>
      </div>
    </div>
  );
}
