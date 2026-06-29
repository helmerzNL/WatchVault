import { useState } from "react";
import { useApp } from "../lib/app";
import { api, ApiError } from "../lib/api";
import { useFetch } from "../lib/useFetch";
import { addPasskey } from "../lib/auth";
import { Section } from "../components/ui";
import { ACCENTS, fmtDate } from "../lib/format";

function Appearance() {
  const { prefs, savePrefs } = useApp();
  return (
    <Section title="Appearance">
      <div className="card col" style={{ gap: 18 }}>
        <div>
          <label>Theme</label>
          <div className="seg">
            {(["light", "dark", "system"] as const).map((t) => (
              <button key={t} className={prefs.theme === t ? "active" : ""}
                onClick={() => savePrefs({ theme: t })} style={{ textTransform: "capitalize" }}>{t}</button>
            ))}
          </div>
        </div>
        <div>
          <label>Accent color</label>
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
  const [name, setName] = useState(user?.household_name || "");
  if (!can("profiles.manage")) return null;
  return (
    <Section title="Household">
      <div className="card">
        <label>Household name</label>
        <div className="row" style={{ gap: 10 }}>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="My Household" />
          <button className="btn-ghost" style={{ flexShrink: 0 }} onClick={async () => {
            try { await api.patch("/household", { name }); toast("Saved"); refreshAuth(); }
            catch { toast("Failed", "err"); }
          }}>Save</button>
        </div>
      </div>
    </Section>
  );
}

function Plugins() {
  const { can, toast } = useApp();
  const plugins = useFetch<any[]>(() => api.get("/plugins"), []);
  const [keys, setKeys] = useState<Record<string, string>>({});
  if (!can("plugins.manage")) return null;

  async function saveSecret(id: string) {
    const val = keys[id];
    if (!val?.trim()) return;
    try {
      const res = await api.put(`/plugins/${id}/secrets`, { api_key: val });
      toast(res.configured ? "Plugin configured" : "Saved");
      setKeys((k) => ({ ...k, [id]: "" }));
      plugins.reload();
    } catch (e) { toast(e instanceof ApiError ? e.message : "Failed", "err"); }
  }

  async function toggle(id: string, enabled: boolean) {
    await api.post(`/plugins/${id}/enable`, { enabled });
    plugins.reload();
  }

  return (
    <Section title="Plugins &amp; metadata">
      <div className="card col" style={{ gap: 0 }}>
        {(plugins.data || []).map((p) => (
          <div key={p.id} className="list-row" style={{ flexWrap: "wrap" }}>
            <div className="col" style={{ flex: 1, gap: 2, minWidth: 200 }}>
              <strong>{p.name} <span className="caption">v{p.version}</span></strong>
              <span className="caption">{p.description}</span>
              <span className="caption">
                {p.configured ? "✓ Configured" : "Not configured"} · {p.enabled ? "Enabled" : "Disabled"}
              </span>
            </div>
            <button className="btn-ghost btn-sm" onClick={() => toggle(p.id, !p.enabled)}>
              {p.enabled ? "Disable" : "Enable"}
            </button>
            {p.secret_keys?.length > 0 && (
              <div className="row" style={{ gap: 8, flexBasis: "100%", marginTop: 8 }}>
                <input type="password" placeholder={`${p.name} API key`}
                  value={keys[p.id] || ""} onChange={(e) => setKeys((k) => ({ ...k, [p.id]: e.target.value }))} />
                <button className="btn-ghost btn-sm" style={{ flexShrink: 0 }} onClick={() => saveSecret(p.id)}>Save key</button>
              </div>
            )}
          </div>
        ))}
        {plugins.data && plugins.data.length === 0 && <p className="muted">No plugins installed.</p>}
      </div>
      <p className="caption" style={{ marginTop: 10 }}>
        TMDB enriches titles with posters, genres and cast. Only public title names are sent — never your watch history.
      </p>
    </Section>
  );
}

function Tokens() {
  const { toast } = useApp();
  const tokens = useFetch<any[]>(() => api.get("/tokens"), []);
  const [name, setName] = useState("");
  const [fresh, setFresh] = useState<string | null>(null);

  async function create() {
    try {
      const res = await api.post("/tokens", { name: name || "API token" });
      setFresh(res.token); setName(""); tokens.reload();
    } catch { toast("Failed", "err"); }
  }
  async function revoke(id: string) {
    if (!confirm("Revoke this token?")) return;
    await api.del(`/tokens/${id}`); tokens.reload();
  }

  return (
    <Section title="API tokens (MCP)">
      <div className="card">
        <p className="caption" style={{ marginBottom: 14 }}>
          Personal tokens let the MCP server answer questions about your watch history from an AI assistant.
        </p>
        {fresh && (
          <div className="card" style={{ marginBottom: 14, borderColor: "var(--accent)", background: "var(--bg)" }}>
            <span className="caption">Copy this token now — it won't be shown again:</span>
            <div className="code-box" style={{ margin: "8px 0" }}>{fresh}</div>
            <button className="btn-ghost btn-sm" onClick={() => { navigator.clipboard?.writeText(fresh); setFresh(null); }}>Copy &amp; dismiss</button>
          </div>
        )}
        <div className="row" style={{ gap: 10, marginBottom: 14 }}>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Token name (e.g. Claude)" />
          <button className="btn-ghost" style={{ flexShrink: 0 }} onClick={create}>Create</button>
        </div>
        {(tokens.data || []).map((t) => (
          <div key={t.id} className="list-row">
            <div className="col" style={{ flex: 1, gap: 2 }}>
              <strong>{t.name}</strong>
              <span className="caption">{t.prefix}… · created {fmtDate(t.created_at)}
                {t.last_used_at ? ` · used ${fmtDate(t.last_used_at)}` : " · never used"}</span>
            </div>
            <button className="btn-danger btn-sm" onClick={() => revoke(t.id)}>Revoke</button>
          </div>
        ))}
        {tokens.data && tokens.data.length === 0 && <p className="muted">No tokens yet.</p>}
      </div>
    </Section>
  );
}

function Account() {
  const { user, logout, toast } = useApp();
  const [busy, setBusy] = useState(false);
  return (
    <Section title="Account">
      <div className="card col" style={{ gap: 14 }}>
        <div className="row">
          <div className="col" style={{ gap: 2, flex: 1 }}>
            <strong>{user?.display_name}</strong>
            <span className="caption">{user?.is_admin ? "Administrator" : "Member"} · {user?.household_name}</span>
          </div>
        </div>
        <hr className="divider" style={{ margin: 0 }} />
        <div className="row wrap" style={{ gap: 10 }}>
          <button className="btn-ghost" disabled={busy} onClick={async () => {
            setBusy(true);
            try { await addPasskey(); toast("Passkey added"); }
            catch (e) { toast(e instanceof ApiError ? e.message : "Failed", "err"); }
            finally { setBusy(false); }
          }}>Add another passkey</button>
          <button className="btn-danger" onClick={logout}>Sign out</button>
        </div>
      </div>
    </Section>
  );
}

export function Settings() {
  return (
    <>
      <h1 className="large-title" style={{ marginBottom: 8 }}>Settings</h1>
      <Appearance />
      <Household />
      <Plugins />
      <Tokens />
      <Account />
    </>
  );
}
