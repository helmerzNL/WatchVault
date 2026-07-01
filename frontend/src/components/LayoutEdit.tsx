import { useRef, type ReactNode } from "react";
import { useT } from "../lib/i18n";
import { IconEye, IconEyeOff, IconGrip } from "./icons";

// Shared drag-and-drop + hide/show layout editing, used by the Dashboard
// (blocks and the stat-tile grid) and the Overviews page (sections). Each
// surface stores its order/hidden under its own key inside prefs.dashboard_layout
// and drives this helper with its own drag state, so the actual reorder/hide
// logic lives in exactly one place.

export interface StoredLayout { order?: string[]; hidden?: string[] }

export interface DragState<Id extends string> {
  dragId: Id | null;
  overId: Id | null;
  setDragId: (v: Id | null) => void;
  setOverId: (v: Id | null) => void;
}

export interface LayoutHandle<Id extends string> {
  // Ids to render in order: everything (gated) while editing, only visible
  // ones otherwise.
  shown: Id[];
  hidden: Set<string>;
  dragId: Id | null;
  overId: Id | null;
  toggleHide: (id: Id) => void;
  startDrag: (id: Id) => void;
  enter: (id: Id) => void;
  endDrag: () => void;
  drop: (id: Id) => void;
}

export function resolveLayout<Id extends string>(opts: {
  editing: boolean;
  defaultOrder: readonly Id[];
  stored: StoredLayout | undefined;
  persist: (order: Id[], hidden: string[]) => void;
  gate?: (id: Id) => boolean;
  drag: DragState<Id>;
}): LayoutHandle<Id> {
  const { editing, defaultOrder, stored, persist, gate, drag } = opts;

  // Saved order first (valid ids only), then any registry entries the saved
  // layout doesn't mention — so new blocks appear automatically and unknown
  // ids from old layouts are dropped.
  const known = defaultOrder as readonly string[];
  const savedOrder = (stored?.order || []).filter((x): x is Id => known.includes(x));
  const fullOrder: Id[] = [...savedOrder, ...defaultOrder.filter((id) => !savedOrder.includes(id))];
  const hidden = new Set<string>(stored?.hidden || []);
  const gated = gate ? fullOrder.filter(gate) : [...fullOrder];
  const shown = editing ? gated : gated.filter((id) => !hidden.has(id));

  const move = (id: Id, targetId: Id) => {
    if (id === targetId) return;
    const order = [...fullOrder];
    const from = order.indexOf(id);
    const to = order.indexOf(targetId);
    if (from < 0 || to < 0) return;
    order.splice(from, 1);
    order.splice(to, 0, id);
    persist(order, [...hidden]);
  };
  const toggleHide = (id: Id) => {
    const h = new Set(hidden);
    if (h.has(id)) h.delete(id); else h.add(id);
    persist(fullOrder, [...h]);
  };

  return {
    shown,
    hidden,
    dragId: drag.dragId,
    overId: drag.overId,
    toggleHide,
    startDrag: (id) => drag.setDragId(id),
    enter: (id) => drag.setOverId(id),
    endDrag: () => { drag.setDragId(null); drag.setOverId(null); },
    drop: (id) => {
      if (drag.dragId) move(drag.dragId, id);
      drag.setDragId(null);
      drag.setOverId(null);
    },
  };
}

// Edit-mode wrapper: a control bar (drag handle + hide/show) above each item.
// Reordering is done by dragging the grip onto another item (native HTML5
// drag-and-drop). Hidden items stay listed (dimmed) so they can be toggled
// back on. `compact` renders the tighter tile variant (used for stat tiles)
// and drops the label; drag events stop propagation so nested tile drags don't
// bubble to an enclosing block's drop zone.
export function EditBlock<Id extends string>({
  id, label, ctrl, compact, children,
}: {
  id: Id;
  label?: string;
  ctrl: LayoutHandle<Id>;
  compact?: boolean;
  children: ReactNode;
}) {
  const { t } = useT();
  const ref = useRef<HTMLDivElement>(null);
  const hidden = ctrl.hidden.has(id);
  const dragging = ctrl.dragId === id;
  const over = ctrl.overId === id && ctrl.dragId !== id && ctrl.dragId != null;
  const sz = compact ? 15 : 18;
  return (
    <div
      ref={ref}
      className={`${compact ? "stat-edit" : "dash-edit-block"} ${hidden ? "is-hidden" : ""} ${dragging ? "is-dragging" : ""} ${over ? "is-over" : ""}`}
      onDragEnter={(e) => { e.preventDefault(); e.stopPropagation(); ctrl.enter(id); }}
      onDragOver={(e) => { e.preventDefault(); e.stopPropagation(); }}
      onDrop={(e) => { e.preventDefault(); e.stopPropagation(); ctrl.drop(id); }}
    >
      <div className={compact ? "stat-edit-bar" : "dash-edit-bar"}>
        <span
          className="dash-edit-grip"
          draggable
          onDragStart={(e) => {
            e.stopPropagation();
            e.dataTransfer.effectAllowed = "move";
            e.dataTransfer.setData("text/plain", id);
            if (ref.current) e.dataTransfer.setDragImage(ref.current, 24, 24);
            ctrl.startDrag(id);
          }}
          onDragEnd={(e) => { e.stopPropagation(); ctrl.endDrag(); }}
          title={t("dashboard.dragReorder")}
          aria-label={t("dashboard.dragReorder")}
        >
          <IconGrip width={sz} height={sz} />
        </span>
        {label && <span className="dash-edit-label">{label}</span>}
        <div className="spacer" style={{ flex: 1 }} />
        <button
          className="btn-ghost btn-sm dash-edit-btn"
          onClick={() => ctrl.toggleHide(id)}
          title={hidden ? t("dashboard.showBlock") : t("dashboard.hideBlock")}
          aria-label={hidden ? t("dashboard.showBlock") : t("dashboard.hideBlock")}
        >
          {hidden ? <IconEyeOff width={sz - 2} height={sz - 2} /> : <IconEye width={sz - 2} height={sz - 2} />}
        </button>
      </div>
      {compact ? children : <div className="dash-edit-body">{children}</div>}
    </div>
  );
}
