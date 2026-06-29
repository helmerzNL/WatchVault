import { useState } from "react";
import { useApp } from "../lib/app";
import { LANGUAGES, useT } from "../lib/i18n";

export function LanguagePicker() {
  const { prefs, savePrefs } = useApp();
  const { t } = useT();
  const [open, setOpen] = useState(false);
  const current = LANGUAGES.find((l) => l.code === prefs.language) || LANGUAGES[1];
  const Flag = current.Flag;

  return (
    <div style={{ position: "relative" }}>
      <button className="btn-ghost btn-sm" onClick={() => setOpen((o) => !o)}
        aria-haspopup="listbox" aria-expanded={open} aria-label={t("common.language")}>
        <Flag style={{ borderRadius: 3, flexShrink: 0 }} />
        <span style={{ textTransform: "uppercase", fontSize: "0.78rem", fontWeight: 700, letterSpacing: "0.04em" }}>
          {current.code}
        </span>
      </button>
      {open && (
        <>
          <div style={{ position: "fixed", inset: 0, zIndex: 90 }} onClick={() => setOpen(false)} />
          <div className="glass" style={{
            position: "absolute", right: 0, top: "calc(100% + 8px)", zIndex: 100,
            minWidth: 200, padding: 8, borderRadius: 16,
          }} role="listbox">
            {LANGUAGES.map((l) => {
              const LFlag = l.Flag;
              return (
                <button key={l.code} className="menu-row" data-active={l.code === current.code}
                  onClick={() => { savePrefs({ language: l.code }); setOpen(false); }}>
                  <LFlag style={{ borderRadius: 3, flexShrink: 0 }} />
                  <span className="col" style={{ gap: 0, alignItems: "flex-start" }}>
                    <strong>{l.native}</strong>
                  </span>
                </button>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
