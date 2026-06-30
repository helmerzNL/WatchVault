import { useApp } from "../lib/app";
import { LANGUAGES, useT } from "../lib/i18n";
import { Dropdown } from "./Menu";

export function LanguagePicker() {
  const { prefs, savePrefs } = useApp();
  const { t } = useT();
  const current = LANGUAGES.find((l) => l.code === prefs.language) || LANGUAGES[1];
  const Flag = current.Flag;

  return (
    <Dropdown
      align="right"
      minWidth={200}
      buttonClassName="btn-ghost btn-sm"
      buttonProps={{ "aria-label": t("common.language") }}
      button={() => (
        <>
          <Flag style={{ borderRadius: 3, flexShrink: 0 }} />
          <span style={{ textTransform: "uppercase", fontSize: "0.78rem", fontWeight: 700, letterSpacing: "0.04em" }}>
            {current.code}
          </span>
        </>
      )}
    >
      {(close) =>
        LANGUAGES.map((l) => {
          const LFlag = l.Flag;
          return (
            <button key={l.code} className="menu-row" data-active={l.code === current.code}
              onClick={() => { savePrefs({ language: l.code }); close(); }}>
              <LFlag style={{ borderRadius: 3, flexShrink: 0 }} />
              <span className="col" style={{ gap: 0, alignItems: "flex-start" }}>
                <strong>{l.native}</strong>
              </span>
            </button>
          );
        })
      }
    </Dropdown>
  );
}
