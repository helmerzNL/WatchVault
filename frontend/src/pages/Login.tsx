import { useState } from "react";
import { useApp } from "../lib/app";
import { useT } from "../lib/i18n";
import { loginPasskey, recoverWithCode, registerPasskey, passkeysSupported } from "../lib/auth";
import { ApiError } from "../lib/api";
import { addPasskey } from "../lib/auth";

type Mode = "login" | "register" | "recover";

export function Login() {
  const { bootstrapped, refreshAuth, toast } = useApp();
  const { t } = useT();
  const [mode, setMode] = useState<Mode>(bootstrapped ? "login" : "register");
  const [name, setName] = useState("");
  const [invite, setInvite] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [recoveryCodes, setRecoveryCodes] = useState<string[] | null>(null);

  const supported = passkeysSupported();

  function fail(e: unknown) {
    const m = e instanceof ApiError ? e.message : e instanceof Error ? e.message : String(e);
    setErr(m);
  }

  async function doLogin() {
    setBusy(true); setErr(null);
    try {
      await loginPasskey();
      await refreshAuth();
    } catch (e) { fail(e); } finally { setBusy(false); }
  }

  async function doRegister() {
    if (!name.trim()) { setErr(t("login.enterName")); return; }
    setBusy(true); setErr(null);
    try {
      const res = await registerPasskey(name.trim(), invite.trim() || undefined);
      if (res.recovery_codes) setRecoveryCodes(res.recovery_codes);
      else { await refreshAuth(); }
    } catch (e) { fail(e); } finally { setBusy(false); }
  }

  async function doRecover() {
    if (!code.trim()) { setErr(t("login.enterRecovery")); return; }
    setBusy(true); setErr(null);
    try {
      await recoverWithCode(code.trim());
      // recovered session is active — let the user enroll a passkey now
      await addPasskey("Recovered passkey").catch(() => {});
      await refreshAuth();
      toast(t("login.welcomeBack"));
    } catch (e) { fail(e); } finally { setBusy(false); }
  }

  if (recoveryCodes) {
    return (
      <div className="center-screen">
        <div className="card" style={{ maxWidth: 460, width: "100%" }}>
          <h1 className="title" style={{ marginBottom: 8 }}>{t("login.saveRecoveryCodes")}</h1>
          <p className="muted" style={{ marginBottom: 16 }}>
            {t("login.saveRecoveryHelp")}
          </p>
          <div className="code-box" style={{ marginBottom: 16, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 }}>
            {recoveryCodes.map((c) => <div key={c}>{c}</div>)}
          </div>
          <button className="btn-primary" style={{ width: "100%" }}
            onClick={async () => { navigator.clipboard?.writeText(recoveryCodes.join("\n")); await refreshAuth(); }}>
            {t("login.savedContinue")}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="center-screen">
      <div className="card" style={{ maxWidth: 420, width: "100%" }}>
        <div className="brand" style={{ fontSize: "1.5rem", marginBottom: 6 }}>
          <img src="/favicon.svg" alt="" style={{ width: 36, height: 36 }} />
          <span>WatchVault</span>
        </div>
        <p className="muted" style={{ marginBottom: 20 }}>{t("common.tagline")}</p>

        {!supported && (
          <p className="toast err" style={{ position: "static", transform: "none", marginBottom: 16 }}>
            {t("login.noPasskeys")}
          </p>
        )}

        {mode === "login" && (
          <div className="col" style={{ gap: 14 }}>
            <button className="btn-primary" disabled={busy || !supported} onClick={doLogin}>
              {busy ? "…" : t("login.signInPasskey")}
            </button>
            <div className="row" style={{ justifyContent: "space-between" }}>
              <button className="btn-ghost btn-sm" onClick={() => { setMode("register"); setErr(null); }}>
                {t("login.joinHousehold")}
              </button>
              <button className="btn-ghost btn-sm" onClick={() => { setMode("recover"); setErr(null); }}>
                {t("login.useRecoveryCode")}
              </button>
            </div>
          </div>
        )}

        {mode === "register" && (
          <div className="col" style={{ gap: 14 }}>
            {!bootstrapped && (
              <p className="caption">{t("login.firstHere")}</p>
            )}
            <div>
              <label>{t("login.yourName")}</label>
              <input value={name} onChange={(e) => setName(e.target.value)} placeholder={t("login.yourNamePlaceholder")}
                autoFocus onKeyDown={(e) => e.key === "Enter" && doRegister()} />
            </div>
            {bootstrapped && (
              <div>
                <label>{t("login.inviteCode")}</label>
                <input value={invite} onChange={(e) => setInvite(e.target.value)} placeholder={t("login.optional")} />
              </div>
            )}
            <button className="btn-primary" disabled={busy || !supported} onClick={doRegister}>
              {busy ? "…" : t("login.createPasskey")}
            </button>
            {bootstrapped && (
              <button className="btn-ghost btn-sm" onClick={() => { setMode("login"); setErr(null); }}>
                {t("login.backToSignIn")}
              </button>
            )}
          </div>
        )}

        {mode === "recover" && (
          <div className="col" style={{ gap: 14 }}>
            <div>
              <label>{t("login.recoveryCode")}</label>
              <input value={code} onChange={(e) => setCode(e.target.value)} placeholder="XXXX-XXXX-XXXX"
                autoFocus onKeyDown={(e) => e.key === "Enter" && doRecover()} />
            </div>
            <button className="btn-primary" disabled={busy} onClick={doRecover}>
              {busy ? "…" : t("login.recoverAddPasskey")}
            </button>
            <button className="btn-ghost btn-sm" onClick={() => { setMode("login"); setErr(null); }}>
              {t("login.backToSignIn")}
            </button>
          </div>
        )}

        {err && <p style={{ color: "#ff453a", marginTop: 16, fontSize: "0.9rem" }}>{err}</p>}
      </div>
    </div>
  );
}
