import { useState } from "react";
import { useApp } from "../lib/app";
import { useT, LANGUAGES } from "../lib/i18n";
import { api, ApiError } from "../lib/api";
import { useFetch } from "../lib/useFetch";
import { addPasskey } from "../lib/auth";
import { Section } from "../components/ui";
import { ACCENTS, fmtDate } from "../lib/format";

function Appearance() {
  const { prefs, savePrefs } = useApp();
  const { t } = useT();
  return (
    <Section title={t("settings.appearance")}>
      <div className="card col" style={{ gap: 18 }}>
        <div>
          <label>{t("settings.theme")}</label>
          <div className="seg">
            {(["light", "dark", "system"] as const).map((th) => (
              <button key={th} className={prefs.theme === th ? "active" : ""}
                onClick={() => savePrefs({ theme: th })}>{t(`settings.${th}`)}</button>
            ))}
          </div>
        </div>
        <div>
          <label>{t("settings.language")}</label>
          <div className="seg" style={{ flexWrap: "wrap" }}>
            {LANGUAGES.map((l) => {
              const Flag = l.Flag;
              return (
                <button key={l.code} className={prefs.language === l.code ? "active" : ""}
                  onClick={() => savePrefs({ language: l.code })}
                  style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                  <Flag style={{ borderRadius: 2 }} /> {l.native}
                </button>
              );
            })}
          </div>
          <span className="caption" style={{ display: "block", marginTop: 6 }}>{t("settings.languageHelp")}</span>
        </div>
        <div>
          <label>{t("settings.accentColor")}</label>
          <div className="swatches">
            {ACCENTS.map((a) => (
              <span key={a.value} className={`swatch ${prefs.accent === a.value ? "active" : ""}`}
                style={{ background: a.value }} title={a.name} onClick={() => savePrefs({ accent: a.value })} />
            ))}
            <label className="swatch" style={{ background: "var(--bg)", border: "2px dashed var(--hairline-strong)", position: "relative", overflow: "hidden" }} title="Custom">
              <input type="color" value={prefs.accent} onChange={(e) => savePrefs({ accent: e.target.value })}
                style={{ opacity: 0, width: "100%", height: "100%", minHeight: 0, cursor: "pointer" }} />
            </label>
          </div>
        </div>
      </div>
    </Section>
  );
}

function Household() {
  const { user, can, toast, refreshAuth } = useApp();
  const { t } = useT();
  const [name, setName] = useState(user?.household_name || "");
  if (!can("profiles.manage")) return null;
  return (
    <Section title={t("settings.household")}>
      <div className="card">
        <label>{t("settings.householdName")}</label>
        <div className="row" style={{ gap: 10 }}>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder={t("settings.householdPlaceholder")} />
          <button className="btn-ghost" style={{ flexShrink: 0 }} onClick={async () => {
            try { await api.patch("/household", { name }); toast(t("settings.saved")); refreshAuth(); }
            catch { toast(t("settings.failed"), "err"); }
          }}>{t("common.save")}</button>
        </div>
      </div>
    </Section>
  );
}

function Plugins() {
  const { can, toast } = useApp();
  const { t } = useT();
  const plugins = useFetch<any[]>(() => api.get("/plugins"), []);
  const [keys, setKeys] = useState<Record<string, string>>({});
  if (!can("plugins.manage")) return null;

  async function saveSecret(id: string) {
    const val = keys[id];
    if (!val?.trim()) return;
    try {
      const res = await api.put(`/plugins/${id}/secrets`, { api_key: val });
      toast(res.configured ? t("settings.pluginConfigured") : t("settings.saved"));
      setKeys((k) => ({ ...k, [id]: "" }));
      plugins.reload();
    } catch (e) { toast(e instanceof ApiError ? e.message : t("settings.failed"), "err"); }
  }

  async function toggle(id: string, enabled: boolean) {
    await api.post(`/plugins/${id}/enable`, { enabled });
    plugins.reload();
  }

  return (
    <Section title={t("settings.plugins")}>
      <div className="card col" style={{ gap: 0 }}>
        {(plugins.data || []).map((p) => (
          <div key={p.id} className="list-row" style={{ flexWrap: "wrap" }}>
            <div className="col" style={{ flex: 1, gap: 2, minWidth: 200 }}>
              <strong>{p.name} <span className="caption">v{p.version}</span></strong>
              <span className="caption">{p.description}</span>
              <span className="caption">
                {p.configured ? t("settings.configured") : t("settings.notConfigured")} · {p.enabled ? t("settings.enabled") : t("settings.disabled")}
              </span>
            </div>
            <button className="btn-ghost btn-sm" onClick={() => toggle(p.id, !p.enabled)}>
              {p.enabled ? t("settings.disable") : t("settings.enable")}
            </button>
            {p.secret_keys?.length > 0 && (
              <div className="row" style={{ gap: 8, flexBasis: "100%", marginTop: 8 }}>
                <input type="password" placeholder={t("settings.apiKeyPlaceholder", { name: p.name })}
                  value={keys[p.id] || ""} onChange={(e) => setKeys((k) => ({ ...k, [p.id]: e.target.value }))} />
                <button className="btn-ghost btn-sm" style={{ flexShrink: 0 }} onClick={() => saveSecret(p.id)}>{t("settings.saveKey")}</button>
              </div>
            )}
          </div>
        ))}
        {plugins.data && plugins.data.length === 0 && <p className="muted">{t("settings.noPlugins")}</p>}
      </div>
      <p className="caption" style={{ marginTop: 10 }}>
        {t("settings.pluginsHelp")}
      </p>
    </Section>
  );
}

function Tokens() {
  const { toast } = useApp();
  const { t } = useT();
  const tokens = useFetch<any[]>(() => api.get("/tokens"), []);
  const [name, setName] = useState("");
  const [fresh, setFresh] = useState<string | null>(null);

  async function create() {
    try {
      const res = await api.post("/tokens", { name: name || "API token" });
      setFresh(res.token); setName(""); tokens.reload();
    } catch { toast(t("settings.failed"), "err"); }
  }
  async function revoke(id: string) {
    if (!confirm(t("settings.revokeConfirm"))) return;
    await api.del(`/tokens/${id}`); tokens.reload();
  }

  return (
    <Section title={t("settings.tokens")}>
      <div className="card">
        <p className="caption" style={{ marginBottom: 14 }}>
          {t("settings.tokensHelp")}
        </p>
        {fresh && (
          <div className="card" style={{ marginBottom: 14, borderColor: "var(--accent)", background: "var(--bg)" }}>
            <span className="caption">{t("settings.copyTokenWarn")}</span>
            <div className="code-box" style={{ margin: "8px 0" }}>{fresh}</div>
            <button className="btn-ghost btn-sm" onClick={() => { navigator.clipboard?.writeText(fresh); setFresh(null); }}>{t("profiles.copyDismiss")}</button>
          </div>
        )}
        <div className="row" style={{ gap: 10, marginBottom: 14 }}>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder={t("settings.tokenNamePlaceholder")} />
          <button className="btn-ghost" style={{ flexShrink: 0 }} onClick={create}>{t("settings.create")}</button>
        </div>
        {(tokens.data || []).map((tk) => (
          <div key={tk.id} className="list-row">
            <div className="col" style={{ flex: 1, gap: 2 }}>
              <strong>{tk.name}</strong>
              <span className="caption">{tk.prefix}… · {t("settings.created", { date: fmtDate(tk.created_at) })}
                {tk.last_used_at ? ` · ${t("settings.used", { date: fmtDate(tk.last_used_at) })}` : ` · ${t("settings.neverUsed")}`}</span>
            </div>
            <button className="btn-danger btn-sm" onClick={() => revoke(tk.id)}>{t("settings.revoke")}</button>
          </div>
        ))}
        {tokens.data && tokens.data.length === 0 && <p className="muted">{t("settings.noTokens")}</p>}
      </div>
    </Section>
  );
}

function Account() {
  const { user, logout, toast } = useApp();
  const { t } = useT();
  const [busy, setBusy] = useState(false);
  return (
    <Section title={t("settings.account")}>
      <div className="card col" style={{ gap: 14 }}>
        <div className="row">
          <div className="col" style={{ gap: 2, flex: 1 }}>
            <strong>{user?.display_name}</strong>
            <span className="caption">{user?.is_admin ? t("settings.administrator") : t("settings.member")} · {user?.household_name}</span>
          </div>
        </div>
        <hr className="divider" style={{ margin: 0 }} />
        <div className="row wrap" style={{ gap: 10 }}>
          <button className="btn-ghost" disabled={busy} onClick={async () => {
            setBusy(true);
            try { await addPasskey(); toast(t("settings.passkeyAdded")); }
            catch (e) { toast(e instanceof ApiError ? e.message : t("settings.failed"), "err"); }
            finally { setBusy(false); }
          }}>{t("settings.addPasskey")}</button>
          <button className="btn-danger" onClick={logout}>{t("settings.signOut")}</button>
        </div>
      </div>
    </Section>
  );
}

export function Settings() {
  const { t } = useT();
  return (
    <>
      <h1 className="large-title" style={{ marginBottom: 8 }}>{t("settings.title")}</h1>
      <Appearance />
      <Household />
      <Plugins />
      <Tokens />
      <Account />
    </>
  );
}
