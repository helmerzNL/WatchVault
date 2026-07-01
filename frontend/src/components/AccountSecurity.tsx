import { useState } from "react";
import { useApp } from "../lib/app";
import { useT } from "../lib/i18n";
import { api, ApiError } from "../lib/api";
import { useFetch } from "../lib/useFetch";
import { fmtDate } from "../lib/format";
import {
  addPasskey,
  passkeysSupported,
  listPasskeys,
  deletePasskey,
  regenerateRecoveryCodes,
  type PasskeyInfo,
} from "../lib/auth";
import { Section } from "./ui";

/** Personal account-security sections for the logged-in user:
 *  API tokens (MCP), passkeys, and recovery codes. */
export function AccountSecurity() {
  return (
    <>
      <ApiTokens />
      <Security />
    </>
  );
}

function ApiTokens() {
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

function Security() {
  const { toast } = useApp();
  const { t } = useT();
  const passkeys = useFetch<PasskeyInfo[]>(() => listPasskeys(), []);
  const [pkName, setPkName] = useState("");
  const [busy, setBusy] = useState(false);
  const [codes, setCodes] = useState<string[] | null>(null);
  const [regenBusy, setRegenBusy] = useState(false);

  async function add() {
    setBusy(true);
    try { await addPasskey(pkName.trim() || undefined); setPkName(""); toast(t("settings.passkeyAdded")); passkeys.reload(); }
    catch (e) { toast(e instanceof ApiError ? e.message : t("settings.failed"), "err"); }
    finally { setBusy(false); }
  }
  async function remove(id: string) {
    if (!confirm(t("settings.deletePasskeyConfirm"))) return;
    try { await deletePasskey(id); passkeys.reload(); }
    catch (e) { toast(e instanceof ApiError ? e.message : t("settings.failed"), "err"); }
  }
  async function regenerate() {
    if (!confirm(t("settings.regenerateConfirm"))) return;
    setRegenBusy(true);
    try { setCodes(await regenerateRecoveryCodes()); }
    catch (e) { toast(e instanceof ApiError ? e.message : t("settings.failed"), "err"); }
    finally { setRegenBusy(false); }
  }

  const items = passkeys.data || [];
  const canDelete = items.length > 1;
  return (
    <Section title={t("settings.security")}>
      <div className="card col" style={{ gap: 0 }}>
        {/* Passkeys */}
        <span className="headline">{t("settings.passkeys")}</span>
        <p className="caption" style={{ margin: "6px 0 14px" }}>{t("settings.passkeysHelp")}</p>
        {items.map((pk) => (
          <div key={pk.id} className="list-row">
            <div className="col" style={{ flex: 1, gap: 2 }}>
              <strong>{pk.name}</strong>
              <span className="caption">{t("settings.created", { date: fmtDate(pk.created_at) })}
                {pk.last_used_at ? ` · ${t("settings.used", { date: fmtDate(pk.last_used_at) })}` : ` · ${t("settings.neverUsed")}`}</span>
            </div>
            <button
              className="btn-danger btn-sm"
              disabled={!canDelete}
              title={!canDelete ? t("settings.lastPasskey") : undefined}
              onClick={() => remove(pk.id)}
            >{t("settings.deletePasskey")}</button>
          </div>
        ))}
        {passkeys.data && items.length === 0 && <p className="muted">{t("settings.noPasskeys")}</p>}
        {passkeysSupported() && (
          <div className="row" style={{ gap: 10, marginTop: 14 }}>
            <input
              value={pkName}
              onChange={(e) => setPkName(e.target.value)}
              placeholder={t("settings.passkeyNamePlaceholder")}
              onKeyDown={(e) => { if (e.key === "Enter" && !busy) add(); }}
            />
            <button className="btn-ghost" style={{ flexShrink: 0 }} disabled={busy} onClick={add}>
              {t("settings.addPasskey")}
            </button>
          </div>
        )}

        <hr className="divider" style={{ margin: "20px 0" }} />

        {/* Recovery codes */}
        <span className="headline">{t("settings.recoveryCodes")}</span>
        <p className="caption" style={{ margin: "6px 0 14px" }}>{t("settings.recoveryCodesHelp")}</p>
        {codes && (
          <div className="card" style={{ marginBottom: 14, borderColor: "var(--accent)", background: "var(--bg)" }}>
            <span className="caption">{t("settings.recoveryCodesWarn")}</span>
            <div className="col" style={{ gap: 6, margin: "10px 0" }}>
              {codes.map((c) => <div key={c} className="code-box">{c}</div>)}
            </div>
            <button className="btn-ghost btn-sm" onClick={() => { navigator.clipboard?.writeText(codes.join("\n")); setCodes(null); }}>
              {t("profiles.copyDismiss")}
            </button>
          </div>
        )}
        <button className="btn-ghost" style={{ alignSelf: "flex-start" }} disabled={regenBusy} onClick={regenerate}>
          {regenBusy ? "…" : t("settings.regenerateCodes")}
        </button>
      </div>
    </Section>
  );
}
