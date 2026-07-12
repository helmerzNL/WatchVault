import { useState } from "react";
import { useApp } from "../lib/app";
import { useT } from "../lib/i18n";
import { Poster } from "./ui";
import { IconChevron, IconGrip } from "./icons";

// A poster grid for "watched titles" lists (per month / per day) that folds every
// title without a TMDB match into a single collapsible, draggable "Unknown" card.
// Matched titles render as normal posters; the Unknown card sits at a saved
// position (prefs.unknown_pos[posKey], default = end) and can be dragged onto any
// cell to move it. It starts collapsed; expanding reveals the unmatched titles
// as their own poster grid below.

export interface WatchedItem {
  id: string;
  title: string;
  kind?: string;
  year?: number | null;
  poster?: string | null;
  matched?: boolean;
  episodes?: number;
  hours?: number;
  [k: string]: any;
}

const UNKNOWN = "__unknown__";

export function WatchedGrid({ items, posKey, subtitle, badge }: {
  items: WatchedItem[];
  posKey: "month" | "day";
  subtitle: (it: WatchedItem) => string;
  badge?: (it: WatchedItem) => string | undefined;
}) {
  const { t } = useT();
  const { prefs, savePrefs } = useApp();
  const [expanded, setExpanded] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [overId, setOverId] = useState<string | null>(null);

  // "TV Kijken" titles have no TMDB match by design, but they are recognised (the
  // household categorised them), so they render as their own tile with the
  // "N× · Xh" subtitle rather than being folded into the collapsed Unknown card.
  const matched = items.filter((i) => i.matched !== false || i.kind === "tv");
  const unknown = items.filter((i) => i.matched === false && i.kind !== "tv");

  // No unrecognized titles → a plain poster grid, nothing special to fold.
  if (unknown.length === 0) {
    return (
      <div className="poster-grid">
        {matched.map((it) => (
          <Poster key={it.id} to={`/title/${it.id}`} poster={it.poster} title={it.title}
            kind={it.kind} enrichId={it.id} unknown={it.unknown} subtitle={subtitle(it)} badge={badge?.(it)} />
        ))}
      </div>
    );
  }

  const savedPos = prefs.unknown_pos?.[posKey];
  const pos = Math.min(Math.max(savedPos ?? matched.length, 0), matched.length);
  const matchedIds = matched.map((m) => m.id);
  const order = [...matchedIds.slice(0, pos), UNKNOWN, ...matchedIds.slice(pos)];
  const byId = new Map(matched.map((m) => [m.id, m]));

  const move = (targetId: string) => {
    if (targetId === UNKNOWN) return;
    const arr = [...order];
    const from = arr.indexOf(UNKNOWN);
    const to = arr.indexOf(targetId);
    if (to < 0 || from === to) return;
    arr.splice(from, 1);
    arr.splice(to, 0, UNKNOWN);
    const newPos = arr.indexOf(UNKNOWN);
    savePrefs({ unknown_pos: { ...(prefs.unknown_pos || {}), [posKey]: newPos } }).catch(() => {});
  };

  const epsTotal = unknown.reduce((n, u) => n + (u.episodes || 0), 0);

  const cell = (id: string) => {
    if (id !== UNKNOWN) {
      const it = byId.get(id)!;
      return (
        <Poster to={`/title/${it.id}`} poster={it.poster} title={it.title}
          kind={it.kind} enrichId={it.id} unknown={it.unknown} subtitle={subtitle(it)} badge={badge?.(it)} />
      );
    }
    return (
      <div
        className={`poster-tile unknown-tile ${dragging ? "is-dragging" : ""}`}
        role="button"
        tabIndex={0}
        aria-expanded={expanded}
        draggable
        onDragStart={(e) => {
          e.dataTransfer.effectAllowed = "move";
          e.dataTransfer.setData("text/plain", UNKNOWN);
          setDragging(true);
        }}
        onDragEnd={() => { setDragging(false); setOverId(null); }}
        onClick={() => setExpanded((v) => !v)}
        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setExpanded((v) => !v); } }}
      >
        <div className="poster">
          <div className="ph unknown-ph">
            <span className="unknown-mark">?</span>
            <span className="unknown-count">{unknown.length}</span>
          </div>
          <span className="unknown-grip" title={t("dashboard.dragReorder")} aria-hidden="true">
            <IconGrip width={16} height={16} />
          </span>
          <span className={`unknown-chevron ${expanded ? "open" : ""}`} aria-hidden="true">
            <IconChevron width={16} height={16} />
          </span>
        </div>
        <div className="poster-cap">
          <div className="t">{t("watched.unknown")}</div>
          <div className="s">{t("watched.unknownSub", { count: unknown.length })}</div>
        </div>
      </div>
    );
  };

  return (
    <>
      <div className="poster-grid">
        {order.map((id) => (
          <div
            key={id}
            className={`watched-cell ${dragging && overId === id && id !== UNKNOWN ? "is-over" : ""}`}
            onDragEnter={(e) => { if (dragging) { e.preventDefault(); setOverId(id); } }}
            onDragOver={(e) => { if (dragging) e.preventDefault(); }}
            onDrop={(e) => {
              if (!dragging) return;
              e.preventDefault();
              move(id);
              setDragging(false);
              setOverId(null);
            }}
          >
            {cell(id)}
          </div>
        ))}
      </div>

      {expanded && (
        <div className="card unknown-panel">
          <div className="row" style={{ alignItems: "center", marginBottom: 12 }}>
            <strong style={{ flex: 1 }}>{t("watched.unknown")}</strong>
            <button className="btn-ghost btn-sm" onClick={() => setExpanded(false)}
              aria-label={t("watched.collapse")} title={t("watched.collapse")}>
              <IconChevron width={16} height={16} style={{ transform: "rotate(180deg)" }} />
            </button>
          </div>
          <div className="poster-grid">
            {unknown.map((it) => (
              <Poster key={it.id} to={`/title/${it.id}`} poster={it.poster} title={it.title}
                kind={it.kind} enrichId={it.id} subtitle={subtitle(it)} badge={badge?.(it)} />
            ))}
          </div>
        </div>
      )}
    </>
  );
}
