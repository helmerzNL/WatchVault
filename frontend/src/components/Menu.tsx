import {
  useCallback, useEffect, useLayoutEffect, useRef, useState,
  type ButtonHTMLAttributes, type ReactNode,
} from "react";
import { createPortal } from "react-dom";

interface DropdownProps {
  /** Trigger contents; receives the open state so it can render chevrons etc. */
  button: (open: boolean) => ReactNode;
  /** Menu contents; `close` dismisses the menu after a selection. */
  children: (close: () => void) => ReactNode;
  align?: "left" | "right";
  minWidth?: number;
  buttonClassName?: string;
  buttonProps?: ButtonHTMLAttributes<HTMLButtonElement>;
}

// A dropdown whose panel + scrim render through a portal on <body>. This keeps
// the popup out of the top bar's `backdrop-filter` containing block — which on
// iOS Safari otherwise traps the fixed overlay inside the header and nudges the
// sticky bar upward when the menu opens.
export function Dropdown({
  button, children, align = "right", minWidth = 200, buttonClassName, buttonProps,
}: DropdownProps) {
  const ref = useRef<HTMLButtonElement>(null);
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<{ top: number; left?: number; right?: number }>({ top: 0 });

  const place = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const top = r.bottom + 8;
    if (align === "right") {
      setPos({ top, right: Math.max(8, window.innerWidth - r.right) });
    } else {
      setPos({ top, left: Math.min(r.left, window.innerWidth - minWidth - 8) });
    }
  }, [align, minWidth]);

  useLayoutEffect(() => {
    if (!open) return;
    place();
    const onMove = () => place();
    window.addEventListener("scroll", onMove, true);
    window.addEventListener("resize", onMove);
    return () => {
      window.removeEventListener("scroll", onMove, true);
      window.removeEventListener("resize", onMove);
    };
  }, [open, place]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  const close = useCallback(() => setOpen(false), []);

  return (
    <>
      <button
        ref={ref}
        type="button"
        className={buttonClassName}
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="listbox"
        aria-expanded={open}
        {...buttonProps}
      >
        {button(open)}
      </button>
      {open && createPortal(
        <div className="dropdown-portal">
          <div className="dropdown-scrim" onClick={close} />
          <div
            className="glass dropdown-menu"
            role="listbox"
            style={{ top: pos.top, left: pos.left, right: pos.right, minWidth }}
          >
            {children(close)}
          </div>
        </div>,
        document.body,
      )}
    </>
  );
}
