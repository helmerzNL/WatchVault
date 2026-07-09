import { useEffect, useRef, useState } from "react";
import { useT } from "../lib/i18n";
import { api, ApiError } from "../lib/api";
import { useApp } from "../lib/app";
import { IconPlus, IconClose } from "./icons";

export interface Tag {
  id: string;
  name: string;
  color?: string | null;
}

// A colored tag chip. When a color is set it tints the chip and shows a dot.
function chipStyle(color?: string | null): React.CSSProperties {
  if (!color) return {};
  return { borderColor: color };
}

export function TagPill({ tag, onRemove }: { tag: Tag; onRemove?: () => void }) {
  const { t } = useT();
  return (
    <span className="chip tag-chip" style={{ minHeight: 0, padding: onRemove ? "3px 6px 3px 10px" : "3px 10px", gap: 6, ...chipStyle(tag.color) }}>
      {tag.color && <span className="tag-dot" style={{ background: tag.color }} />}
      {tag.name}
      {onRemove && (
        <button className="manual-x" title={t("common.remove")} aria-label={t("common.remove")}
          onClick={(e) => { e.preventDefault(); e.stopPropagation(); onRemove(); }}>
          <IconClose width={12} height={12} />
        </button>
      )}
    </span>
  );
}

// Editable tag row for a title / season / episode. Shows assigned tags with a
// remove-x and a "+" that opens a picker of the household's tags (with inline
// create). `attach`/`detach` hit the entity-specific endpoints; local state is
// updated optimistically so the row stays snappy without a full reload.
export function TagChips({ tags, canEdit, attach, detach, onChange }: {
  tags: Tag[];
  canEdit: boolean;
  attach: (tagId: string) => Promise<void>;
  detach: (tagId: string) => Promise<void>;
  onChange?: () => void;
}) {
  const { t } = useT();
  const { toast } = useApp();
  const [assigned, setAssigned] = useState<Tag[]>(tags);
  const [picking, setPicking] = useState(false);
  const [all, setAll] = useState<Tag[] | null>(null);
  const [newName, setNewName] = useState("");
  const [busy, setBusy] = useState(false);
  const boxRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => { setAssigned(tags); }, [tags]);

  // Close the picker on an outside click.
  useEffect(() => {
    if (!picking) return;
    const onDoc = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setPicking(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [picking]);

  async function openPicker() {
    setPicking(true);
    if (all === null) {
      try { setAll(await api.get("/tags")); } catch { setAll([]); }
    }
  }

  async function add(tag: Tag) {
    if (assigned.some((a) => a.id === tag.id)) { setPicking(false); return; }
    setBusy(true);
    try {
      await attach(tag.id);
      setAssigned((a) => [...a, tag].sort((x, y) => x.name.localeCompare(y.name)));
      onChange?.();
    } catch (e) { toast(e instanceof ApiError ? e.message : t("settings.failed"), "err"); }
    finally { setBusy(false); setPicking(false); }
  }

  async function remove(tag: Tag) {
    setAssigned((a) => a.filter((x) => x.id !== tag.id));
    try {
      await detach(tag.id);
      onChange?.();
    } catch (e) {
      setAssigned((a) => [...a, tag].sort((x, y) => x.name.localeCompare(y.name)));
      toast(e instanceof ApiError ? e.message : t("settings.failed"), "err");
    }
  }

  async function createAndAdd() {
    const name = newName.trim();
    if (!name) return;
    setBusy(true);
    try {
      const tag: Tag = await api.post("/tags", { name });
      setAll((list) => [...(list || []), tag].sort((x, y) => x.name.localeCompare(y.name)));
      setNewName("");
      await add(tag);
    } catch (e) { toast(e instanceof ApiError ? e.message : t("settings.failed"), "err"); setBusy(false); }
  }

  const available = (all || []).filter((tg) => !assigned.some((a) => a.id === tg.id));

  return (
    <div className="tag-chips row wrap" style={{ gap: 6, alignItems: "center", position: "relative" }} ref={boxRef}>
      {assigned.map((tag) => (
        <TagPill key={tag.id} tag={tag} onRemove={canEdit ? () => remove(tag) : undefined} />
      ))}
      {canEdit && (
        <button className="chip tag-add" style={{ minHeight: 0, padding: "3px 8px", gap: 4 }}
          onClick={openPicker} title={t("tags.add")} aria-label={t("tags.add")}>
          <IconPlus width={12} height={12} /> {t("tags.add")}
        </button>
      )}
      {picking && (
        <div className="tag-picker card">
          {available.length > 0 && (
            <div className="row wrap" style={{ gap: 6, marginBottom: 8 }}>
              {available.map((tg) => (
                <button key={tg.id} className="chip tag-chip" disabled={busy}
                  style={{ minHeight: 0, padding: "3px 10px", gap: 6, ...chipStyle(tg.color) }}
                  onClick={() => add(tg)}>
                  {tg.color && <span className="tag-dot" style={{ background: tg.color }} />}
                  {tg.name}
                </button>
              ))}
            </div>
          )}
          {all !== null && available.length === 0 && (all || []).length > 0 && (
            <p className="caption" style={{ margin: "0 0 8px" }}>{t("tags.allAssigned")}</p>
          )}
          <div className="row" style={{ gap: 6 }}>
            <input value={newName} onChange={(e) => setNewName(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") createAndAdd(); }}
              placeholder={t("tags.newPlaceholder")} style={{ minHeight: 32, padding: "4px 8px", flex: 1 }} />
            <button className="btn-primary btn-sm" disabled={busy || !newName.trim()} onClick={createAndAdd}>
              {t("tags.create")}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
