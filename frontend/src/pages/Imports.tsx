import { useRef, useState } from "react";
import { useApp } from "../lib/app";
import { useT } from "../lib/i18n";
import { api, ApiError } from "../lib/api";
import { useFetch } from "../lib/useFetch";
import { Loading, Section } from "../components/ui";
import { IconImport, IconRefresh, IconPlus, IconCheck } from "../components/icons";
import { fmtDate } from "../lib/format";

interface ConfigField {
  key: string; label: string; type?: string; placeholder?: string; required?: boolean; help?: string;
}
interface Provider {
  id: string; key: string; name: string; ingest_type: string; adapter: string; color?: string;
  config_fields?: ConfigField[];
}

function FileImport({ providers, onDone }: { providers: Provider[]; onDone: () => void }) {
  const { profiles, user, toast, can } = useApp();
  const { t } = useT();
  const fileProviders = providers.filter((p) => p.ingest_type === "csv" || p.ingest_type === "file");
  const [provider, setProvider] = useState(fileProviders[0]?.key || "");
  const [target, setTarget] = useState(user?.id || "");
  const [busy, setBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  async function submit() {
    const f = fileRef.current?.files?.[0];
    if (!f) { toast(t("imports.chooseFile"), "err"); return; }
    if (!provider) { toast(t("imports.pickProvider"), "err"); return; }
    setBusy(true);
    try {
      const form = new FormData();
      form.set("provider", provider);
      form.set("file", f);
      if (target) form.set("user_id", target);
      const res = await api.upload("/ingest/import", form);
      toast(t("imports.imported", { inserted: res.inserted, duplicates: res.duplicates, titles: res.titles_created }));
      if (fileRef.current) fileRef.current.value = "";
      onDone();
    } catch (e) {
      toast(e instanceof ApiError ? e.message : t("imports.importFailed"), "err");
    } finally { setBusy(false); }
  }

  if (!can("ingest.write")) return null;

  return (
    <div className="card">
      <div className="row" style={{ marginBottom: 14 }}>
        <IconImport width={20} height={20} />
        <span className="headline">{t("imports.importFile")}</span>
      </div>
      <p className="caption" style={{ marginBottom: 16 }}>
        {t("imports.netflixHelp")}
      </p>
      <div className="filters-grid" style={{ marginBottom: 14 }}>
        <div>
          <label>{t("imports.provider")}</label>
          <select value={provider} onChange={(e) => setProvider(e.target.value)}>
            {fileProviders.map((p) => <option key={p.key} value={p.key}>{p.name}</option>)}
          </select>
        </div>
        <div>
          <label>{t("imports.attributeTo")}</label>
          <select value={target} onChange={(e) => setTarget(e.target.value)}>
            {profiles.map((p) => <option key={p.id} value={p.id}>{p.display_name}{p.id === user?.id ? ` (${t("common.you")})` : ""}</option>)}
          </select>
        </div>
      </div>
      <input ref={fileRef} type="file" accept=".csv,.json,.tsv,text/csv,application/json" style={{ marginBottom: 14 }} />
      <button className="btn-primary" disabled={busy} onClick={submit}>
        {busy ? t("imports.importing") : t("imports.importFileBtn")}
      </button>
    </div>
  );
}

function Connections({ providers, connections, reload }: {
  providers: Provider[]; connections: any[]; reload: () => void;
}) {
  const { toast, can } = useApp();
  const { t } = useT();
  const apiProviders = providers.filter((p) => p.ingest_type === "api");
  const [adding, setAdding] = useState(false);
  const [provider, setProvider] = useState(apiProviders[0]?.key || "");
  const [name, setName] = useState("");
  const [config, setConfig] = useState<Record<string, any>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [libs, setLibs] = useState<{ id: string; name: string; type?: string }[] | null>(null);
  const [libBusy, setLibBusy] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);
  const [editLibs, setEditLibs] = useState<{ id: string; name: string; type?: string }[] | null>(null);
  const [editSel, setEditSel] = useState<string[]>([]);
  const [editBusy, setEditBusy] = useState(false);
  const [traktPin, setTraktPin] = useState("");
  const [reauthId, setReauthId] = useState<string | null>(null);
  const [reauthSecret, setReauthSecret] = useState("");

  function providerSupportsLibraries(key: string) {
    return (apiProviders.find((p) => p.key === key)?.config_fields || [])
      .some((f) => f.type === "library_select");
  }

  function providerSupportsTrakt(key: string) {
    return (apiProviders.find((p) => p.key === key)?.config_fields || [])
      .some((f) => f.type === "trakt_oauth");
  }

  async function openEdit(c: any) {
    setEditing(c.id); setEditLibs(null); setEditSel([]); setEditBusy(true);
    try {
      const res = await api.get(`/connections/${c.id}/libraries`);
      setEditLibs(res.libraries || []);
      setEditSel(res.selected || []);
    } catch (e) {
      toast(e instanceof ApiError ? e.message : t("imports.couldNotLoadLibraries"), "err");
      setEditing(null);
    } finally { setEditBusy(false); }
  }

  function toggleEditLib(id: string) {
    setEditSel((s) => s.includes(id) ? s.filter((x) => x !== id) : [...s, id]);
  }

  async function saveEdit(id: string) {
    setEditBusy(true);
    try {
      const res = await api.put(`/connections/${id}`, { config: { library_ids: editSel } });
      toast(res.pruned ? t("imports.librariesUpdatedPruned", { pruned: res.pruned })
                       : t("imports.librariesUpdated"));
      setEditing(null);
      reload();
    } catch (e) {
      toast(e instanceof ApiError ? e.message : t("settings.failed"), "err");
    } finally { setEditBusy(false); }
  }

  const selected = apiProviders.find((p) => p.key === provider);
  const fields = selected?.config_fields || [];

  function pickProvider(key: string) {
    setProvider(key);
    setConfig({});
    setLibs(null);
  }

  function toggleLib(key: string, id: string) {
    setConfig((c) => {
      const cur: string[] = Array.isArray(c[key]) ? c[key] : [];
      return { ...c, [key]: cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id] };
    });
  }

  async function authorizeTrakt() {
    if (!config.client_id || !config.client_secret) {
      toast(t("imports.traktNeedKeys"), "err"); return;
    }
    if (!traktPin.trim()) { toast(t("imports.traktNeedPin"), "err"); return; }
    setBusy("trakt");
    try {
      const res = await api.post("/connections/trakt/authorize", {
        client_id: config.client_id, client_secret: config.client_secret, pin: traktPin.trim(),
      });
      setConfig((c) => ({
        ...c, access_token: res.access_token, refresh_token: res.refresh_token,
        token_expires_at: res.token_expires_at, username: c.username || "me",
      }));
      setTraktPin("");
      toast(t("imports.traktAuthorized"));
    } catch (e) {
      toast(e instanceof ApiError ? e.message : t("settings.failed"), "err");
    } finally { setBusy(null); }
  }

  async function loadLibraries() {    setLibBusy(true);
    try {
      const res = await api.post("/connections/libraries", { provider, config });
      setLibs(res.libraries || []);
      if (!res.libraries?.length) toast(t("imports.noLibrariesFound"), "err");
    } catch (e) {
      toast(e instanceof ApiError ? e.message : t("imports.couldNotLoadLibraries"), "err");
    } finally { setLibBusy(false); }
  }

  async function create() {
    const missing = fields.filter((f) => f.required && !String(config[f.key] ?? "").trim());
    if (missing.length) {
      toast(t("imports.fillIn", { fields: missing.map((f) => f.label).join(", ") }), "err");
      return;
    }
    setBusy("create");
    try {
      await api.post("/connections", { provider, name: name || undefined, config });
      toast(t("imports.connectionAdded"));
      setAdding(false); setName(""); setConfig({}); setLibs(null);
      reload();
    } catch (e) {
      toast(e instanceof ApiError ? e.message : t("settings.failed"), "err");
    } finally { setBusy(null); }
  }

  async function sync(id: string) {
    setBusy(id);
    try {
      const res = await api.post(`/connections/${id}/sync`);
      toast(t("imports.synced", { inserted: res.inserted, duplicates: res.duplicates }));
      reload();
    } catch (e) {
      toast(e instanceof ApiError ? e.message : t("imports.syncFailed"), "err");
      reload();
    } finally { setBusy(null); }
  }

  async function remove(id: string) {
    if (!confirm(t("imports.removeConnectionConfirm"))) return;
    await api.del(`/connections/${id}`);
    reload();
  }

  async function clearItems(id: string) {
    if (!confirm(t("imports.clearItemsConfirm"))) return;
    setBusy(id);
    try {
      const res = await api.post(`/connections/${id}/clear`);
      toast(t("imports.itemsCleared", { removed: res.removed }));
      reload();
    } catch (e) {
      toast(e instanceof ApiError ? e.message : t("settings.failed"), "err");
    } finally { setBusy(null); }
  }

  async function reauthorizeTrakt(c: any) {
    if (!c.client_id) { toast(t("imports.traktNeedKeys"), "err"); return; }
    if (!c.has_secret && !reauthSecret.trim()) { toast(t("imports.traktNeedKeys"), "err"); return; }
    if (!traktPin.trim()) { toast(t("imports.traktNeedPin"), "err"); return; }
    setBusy("reauth");
    try {
      await api.post(`/connections/${c.id}/trakt-authorize`, {
        pin: traktPin.trim(),
        ...(reauthSecret.trim() ? { client_secret: reauthSecret.trim() } : {}),
      });
      setTraktPin(""); setReauthSecret(""); setReauthId(null);
      toast(t("imports.traktAuthorized"));
      reload();
    } catch (e) {
      toast(e instanceof ApiError ? e.message : t("settings.failed"), "err");
    } finally { setBusy(null); }
  }

  return (
    <div className="card">
      <div className="row" style={{ marginBottom: 14 }}>
        <IconRefresh width={20} height={20} />
        <span className="headline">{t("imports.apiConnections")}</span>
        <div className="spacer" />
        {can("ingest.write") && apiProviders.length > 0 && (
          <button className="btn-ghost btn-sm" onClick={() => setAdding((a) => !a)}>
            <IconPlus width={16} height={16} /> {t("common.add")}
          </button>
        )}
      </div>
      <p className="caption" style={{ marginBottom: 16 }}>
        {t("imports.apiHelp")}
      </p>

      {adding && (
        <div className="card" style={{ marginBottom: 16, background: "var(--bg)" }}>
          <div className="filters-grid" style={{ marginBottom: 12 }}>
            <div>
              <label>{t("imports.service")}</label>
              <select value={provider} onChange={(e) => pickProvider(e.target.value)}>
                {apiProviders.map((p) => <option key={p.key} value={p.key}>{p.name}</option>)}
              </select>
            </div>
            <div>
              <label>{t("imports.name")}</label>
              <input value={name} onChange={(e) => setName(e.target.value)} placeholder={selected ? t("imports.householdSuffix", { name: selected.name }) : t("imports.connectionNamePlaceholder")} />
            </div>
          </div>
          {fields.map((f) => (
            f.type === "trakt_oauth" ? (
              <div key={f.key} style={{ marginBottom: 12 }}>
                <label>{t("imports.optionalSuffix", { label: f.label })}</label>
                {config.access_token ? (
                  <div className="caption" style={{ color: "var(--ok, #3ba776)", marginBottom: 6 }}>
                    ✓ {t("imports.traktAuthorized")}
                  </div>
                ) : (
                  <div className="col" style={{ gap: 8 }}>
                    <div className="caption">{t("imports.traktStep1")}{" "}
                      <a href={config.client_id
                        ? `https://trakt.tv/oauth/authorize?response_type=code&client_id=${encodeURIComponent(config.client_id)}&redirect_uri=urn:ietf:wg:oauth:2.0:oob`
                        : undefined}
                        target="_blank" rel="noreferrer"
                        onClick={(e) => { if (!config.client_id) { e.preventDefault(); toast(t("imports.traktNeedKeys"), "err"); } }}>
                        {t("imports.traktOpenAuth")}
                      </a>
                    </div>
                    <div className="row" style={{ gap: 8 }}>
                      <input value={traktPin} onChange={(e) => setTraktPin(e.target.value)}
                        placeholder={t("imports.traktPinPlaceholder")} style={{ flex: 1 }} />
                      <button className="btn-ghost btn-sm" disabled={busy === "trakt"} onClick={authorizeTrakt}>
                        {busy === "trakt" ? t("imports.loadingShort") : t("imports.traktAuthorize")}
                      </button>
                    </div>
                  </div>
                )}
                {f.help && <span className="caption" style={{ display: "block", marginTop: 4 }}>{f.help}</span>}
              </div>
            ) : f.type === "library_select" ? (              <div key={f.key} style={{ marginBottom: 12 }}>
                <label>{t("imports.optionalSuffix", { label: f.label })}</label>
                <div className="row" style={{ gap: 8, marginBottom: libs ? 8 : 0 }}>
                  <button className="btn-ghost btn-sm" disabled={libBusy} onClick={loadLibraries}>
                    {libBusy ? t("imports.loadingShort") : <><IconRefresh width={15} height={15} /> {t("imports.loadLibraries")}</>}
                  </button>
                  {libs && <span className="caption">{t("imports.librariesSelected", { selected: config[f.key]?.length || 0, total: libs.length })}</span>}
                </div>
                {libs && libs.length > 0 && (
                  <div className="col" style={{ gap: 6 }}>
                    {libs.map((lib) => {
                      const sel: string[] = Array.isArray(config[f.key]) ? config[f.key] : [];
                      return (
                        <label key={lib.id} className="row" style={{ gap: 8, cursor: "pointer", fontWeight: 400 }}>
                          <input type="checkbox" checked={sel.includes(lib.id)}
                            onChange={() => toggleLib(f.key, lib.id)} style={{ width: "auto" }} />
                          <span>{lib.name}{lib.type ? <span className="caption"> · {lib.type}</span> : null}</span>
                        </label>
                      );
                    })}
                  </div>
                )}
                {f.help && <span className="caption" style={{ display: "block", marginTop: 4 }}>{f.help}</span>}
              </div>
            ) : (
              <div key={f.key} style={{ marginBottom: 12 }}>
                <label>{f.required ? f.label : t("imports.optionalSuffix", { label: f.label })}</label>
                <input
                  value={config[f.key] || ""}
                  onChange={(e) => setConfig((c) => ({ ...c, [f.key]: e.target.value }))}
                  placeholder={f.placeholder}
                  type={f.type === "password" ? "password" : "text"}
                />
                {f.help && <span className="caption" style={{ display: "block", marginTop: 4 }}>{f.help}</span>}
              </div>
            )
          ))}
          <button className="btn-primary" disabled={busy === "create"} onClick={create}>
            {busy === "create" ? t("common.saving") : t("imports.saveConnection")}
          </button>
        </div>
      )}

      {connections.length === 0 ? (
        <p className="muted">{t("imports.noConnections")}</p>
      ) : (
        <div>
          {connections.map((c) => (
            <div key={c.id} className="col" style={{ gap: 0 }}>
              <div className="list-row">
                <div className="col" style={{ flex: 1, gap: 2 }}>
                  <strong>{c.name}</strong>
                  <span className="caption">
                    {c.provider_name}
                    {c.last_sync_at ? ` · ${t("imports.lastSync", { date: fmtDate(c.last_sync_at) })}` : ` · ${t("imports.neverSynced")}`}
                    {c.last_status ? ` · ${c.last_status}` : ""}
                  </span>
                </div>
                {can("ingest.write") && (
                  <>
                    {providerSupportsLibraries(c.provider_key) && (
                      <button className="btn-ghost btn-sm" disabled={editBusy && editing === c.id}
                        onClick={() => (editing === c.id ? setEditing(null) : openEdit(c))}>
                        {t("imports.editLibraries")}
                      </button>
                    )}
                    {providerSupportsTrakt(c.provider_key) && (
                      <button className="btn-ghost btn-sm"
                        onClick={() => { setReauthId(reauthId === c.id ? null : c.id); setTraktPin(""); setReauthSecret(""); }}>
                        {t("imports.traktReauthorize")}
                      </button>
                    )}
                    <button className="btn-ghost btn-sm" disabled={busy === c.id} onClick={() => sync(c.id)}>
                      {busy === c.id ? "…" : <><IconRefresh width={15} height={15} /> {t("imports.sync")}</>}
                    </button>
                    <button className="btn-ghost btn-sm" disabled={busy === c.id} onClick={() => clearItems(c.id)}>
                      {t("imports.clearItems")}
                    </button>
                    <button className="btn-danger btn-sm" onClick={() => remove(c.id)}>{t("common.remove")}</button>
                  </>
                )}
              </div>
              {editing === c.id && (
                <div className="card" style={{ margin: "0 0 12px", background: "var(--bg)" }}>
                  <label>{t("imports.editLibrariesTitle")}</label>
                  <p className="caption" style={{ marginBottom: 10 }}>{t("imports.editLibrariesHelp")}</p>
                  {editBusy && !editLibs ? (
                    <span className="caption">{t("imports.loadingShort")}</span>
                  ) : editLibs && editLibs.length > 0 ? (
                    <div className="col" style={{ gap: 6, marginBottom: 12 }}>
                      {editLibs.map((lib) => (
                        <label key={lib.id} className="row" style={{ gap: 8, cursor: "pointer", fontWeight: 400 }}>
                          <input type="checkbox" checked={editSel.includes(lib.id)}
                            onChange={() => toggleEditLib(lib.id)} style={{ width: "auto" }} />
                          <span>{lib.name}{lib.type ? <span className="caption"> · {lib.type}</span> : null}</span>
                        </label>
                      ))}
                    </div>
                  ) : (
                    <p className="caption" style={{ marginBottom: 12 }}>{t("imports.noLibrariesFound")}</p>
                  )}
                  <div className="row" style={{ gap: 8 }}>
                    <button className="btn-primary btn-sm" disabled={editBusy} onClick={() => saveEdit(c.id)}>
                      {editBusy ? t("common.saving") : t("imports.saveLibraries")}
                    </button>
                    <button className="btn-ghost btn-sm" onClick={() => setEditing(null)}>{t("common.cancel")}</button>
                    <span className="caption">{t("imports.librariesSelected", { selected: editSel.length, total: editLibs?.length || 0 })}</span>
                  </div>
                </div>
              )}
              {reauthId === c.id && (
                <div className="card" style={{ margin: "0 0 12px", background: "var(--bg)" }}>
                  <label>{t("imports.traktReauthTitle")}</label>
                  <p className="caption" style={{ marginBottom: 10 }}>{t("imports.traktReauthHelp")}</p>
                  <div className="col" style={{ gap: 8 }}>
                    {!c.has_secret && (
                      <input value={reauthSecret} onChange={(e) => setReauthSecret(e.target.value)}
                        type="password" placeholder={t("imports.traktSecretPlaceholder")} />
                    )}
                    <div className="caption">{t("imports.traktStep1")}{" "}
                      <a href={c.client_id
                        ? `https://trakt.tv/oauth/authorize?response_type=code&client_id=${encodeURIComponent(c.client_id)}&redirect_uri=urn:ietf:wg:oauth:2.0:oob`
                        : undefined}
                        target="_blank" rel="noreferrer">
                        {t("imports.traktOpenAuth")}
                      </a>
                    </div>
                    <div className="row" style={{ gap: 8 }}>
                      <input value={traktPin} onChange={(e) => setTraktPin(e.target.value)}
                        placeholder={t("imports.traktPinPlaceholder")} style={{ flex: 1 }} />
                      <button className="btn-primary btn-sm" disabled={busy === "reauth"} onClick={() => reauthorizeTrakt(c)}>
                        {busy === "reauth" ? t("imports.loadingShort") : t("imports.traktAuthorize")}
                      </button>
                      <button className="btn-ghost btn-sm" onClick={() => setReauthId(null)}>{t("common.cancel")}</button>
                    </div>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function Imports() {
  const { can, toast } = useApp();
  const { t } = useT();
  const providers = useFetch<Provider[]>(() => api.get("/providers"), []);
  const connections = useFetch<any[]>(() => api.get("/connections"), []);
  const [rebuilding, setRebuilding] = useState(false);

  async function rebuild() {
    setRebuilding(true);
    try {
      await api.post("/ingest/rebuild-agg");
      toast(t("imports.aggregatesRebuilt"));
    } catch { toast(t("imports.rebuildFailed"), "err"); }
    finally { setRebuilding(false); }
  }

  if (providers.loading) return <Loading />;

  return (
    <>
      <h1 className="large-title" style={{ marginBottom: 16 }}>{t("imports.title")}</h1>
      <div className="col" style={{ gap: 20 }}>
        <FileImport providers={providers.data || []} onDone={() => connections.reload()} />
        <Connections providers={providers.data || []} connections={connections.data || []} reload={connections.reload} />

        {can("settings.manage") && (
          <div className="card">
            <div className="row">
              <div className="col" style={{ gap: 2, flex: 1 }}>
                <span className="headline">{t("imports.maintenance")}</span>
                <span className="caption">{t("imports.maintenanceHelp")}</span>
              </div>
              <button className="btn-ghost btn-sm" disabled={rebuilding} onClick={rebuild}>
                {rebuilding ? "…" : <><IconCheck width={16} height={16} /> {t("imports.rebuildAggregates")}</>}
              </button>
            </div>
          </div>
        )}
      </div>
    </>
  );
}
