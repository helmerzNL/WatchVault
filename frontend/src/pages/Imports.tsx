import { useRef, useState } from "react";
import { useApp } from "../lib/app";
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
  const fileProviders = providers.filter((p) => p.ingest_type === "csv" || p.ingest_type === "file");
  const [provider, setProvider] = useState(fileProviders[0]?.key || "");
  const [target, setTarget] = useState(user?.id || "");
  const [busy, setBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  async function submit() {
    const f = fileRef.current?.files?.[0];
    if (!f) { toast("Choose a file first", "err"); return; }
    if (!provider) { toast("Pick a provider", "err"); return; }
    setBusy(true);
    try {
      const form = new FormData();
      form.set("provider", provider);
      form.set("file", f);
      if (target) form.set("user_id", target);
      const res = await api.upload("/ingest/import", form);
      toast(`Imported ${res.inserted} new (${res.duplicates} duplicates, ${res.titles_created} titles)`);
      if (fileRef.current) fileRef.current.value = "";
      onDone();
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "Import failed", "err");
    } finally { setBusy(false); }
  }

  if (!can("ingest.write")) return null;

  return (
    <div className="card">
      <div className="row" style={{ marginBottom: 14 }}>
        <IconImport width={20} height={20} />
        <span className="headline">Import a file</span>
      </div>
      <p className="caption" style={{ marginBottom: 16 }}>
        Netflix: Account → Profile → <em>Viewing activity</em> → <em>Download all</em>. Drop the CSV here.
        Other services: use a generic CSV/JSON export.
      </p>
      <div className="filters-grid" style={{ marginBottom: 14 }}>
        <div>
          <label>Provider</label>
          <select value={provider} onChange={(e) => setProvider(e.target.value)}>
            {fileProviders.map((p) => <option key={p.key} value={p.key}>{p.name}</option>)}
          </select>
        </div>
        <div>
          <label>Attribute to</label>
          <select value={target} onChange={(e) => setTarget(e.target.value)}>
            {profiles.map((p) => <option key={p.id} value={p.id}>{p.display_name}{p.id === user?.id ? " (you)" : ""}</option>)}
          </select>
        </div>
      </div>
      <input ref={fileRef} type="file" accept=".csv,.json,.tsv,text/csv,application/json" style={{ marginBottom: 14 }} />
      <button className="btn-primary" disabled={busy} onClick={submit}>
        {busy ? "Importing…" : "Import file"}
      </button>
    </div>
  );
}

function Connections({ providers, connections, reload }: {
  providers: Provider[]; connections: any[]; reload: () => void;
}) {
  const { toast, can } = useApp();
  const apiProviders = providers.filter((p) => p.ingest_type === "api");
  const [adding, setAdding] = useState(false);
  const [provider, setProvider] = useState(apiProviders[0]?.key || "");
  const [name, setName] = useState("");
  const [config, setConfig] = useState<Record<string, any>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [libs, setLibs] = useState<{ id: string; name: string; type?: string }[] | null>(null);
  const [libBusy, setLibBusy] = useState(false);

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

  async function loadLibraries() {
    setLibBusy(true);
    try {
      const res = await api.post("/connections/libraries", { provider, config });
      setLibs(res.libraries || []);
      if (!res.libraries?.length) toast("No libraries found for this server", "err");
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "Could not load libraries", "err");
    } finally { setLibBusy(false); }
  }

  async function create() {
    const missing = fields.filter((f) => f.required && !String(config[f.key] ?? "").trim());
    if (missing.length) {
      toast(`Fill in: ${missing.map((f) => f.label).join(", ")}`, "err");
      return;
    }
    setBusy("create");
    try {
      await api.post("/connections", { provider, name: name || undefined, config });
      toast("Connection added");
      setAdding(false); setName(""); setConfig({}); setLibs(null);
      reload();
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "Failed", "err");
    } finally { setBusy(null); }
  }

  async function sync(id: string) {
    setBusy(id);
    try {
      const res = await api.post(`/connections/${id}/sync`);
      toast(`Synced: +${res.inserted} new (${res.duplicates} dup)`);
      reload();
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "Sync failed", "err");
      reload();
    } finally { setBusy(null); }
  }

  async function remove(id: string) {
    if (!confirm("Remove this connection?")) return;
    await api.del(`/connections/${id}`);
    reload();
  }

  return (
    <div className="card">
      <div className="row" style={{ marginBottom: 14 }}>
        <IconRefresh width={20} height={20} />
        <span className="headline">API sync connections</span>
        <div className="spacer" />
        {can("ingest.write") && apiProviders.length > 0 && (
          <button className="btn-ghost btn-sm" onClick={() => setAdding((a) => !a)}>
            <IconPlus width={16} height={16} /> Add
          </button>
        )}
      </div>
      <p className="caption" style={{ marginBottom: 16 }}>
        Plex, Jellyfin &amp; Trakt expose official APIs — connect once and sync watch history on demand.
      </p>

      {adding && (
        <div className="card" style={{ marginBottom: 16, background: "var(--bg)" }}>
          <div className="filters-grid" style={{ marginBottom: 12 }}>
            <div>
              <label>Service</label>
              <select value={provider} onChange={(e) => pickProvider(e.target.value)}>
                {apiProviders.map((p) => <option key={p.key} value={p.key}>{p.name}</option>)}
              </select>
            </div>
            <div>
              <label>Name</label>
              <input value={name} onChange={(e) => setName(e.target.value)} placeholder={selected ? `${selected.name} (household)` : "Connection name"} />
            </div>
          </div>
          {fields.map((f) => (
            f.type === "library_select" ? (
              <div key={f.key} style={{ marginBottom: 12 }}>
                <label>{f.label} (optional)</label>
                <div className="row" style={{ gap: 8, marginBottom: libs ? 8 : 0 }}>
                  <button className="btn-ghost btn-sm" disabled={libBusy} onClick={loadLibraries}>
                    {libBusy ? "Loading…" : <><IconRefresh width={15} height={15} /> Load libraries</>}
                  </button>
                  {libs && <span className="caption">{(config[f.key]?.length || 0)} of {libs.length} selected</span>}
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
                <label>{f.label}{f.required ? "" : " (optional)"}</label>
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
            {busy === "create" ? "Saving…" : "Save connection"}
          </button>
        </div>
      )}

      {connections.length === 0 ? (
        <p className="muted">No connections yet.</p>
      ) : (
        <div>
          {connections.map((c) => (
            <div key={c.id} className="list-row">
              <div className="col" style={{ flex: 1, gap: 2 }}>
                <strong>{c.name}</strong>
                <span className="caption">
                  {c.provider_name}
                  {c.last_sync_at ? ` · last sync ${fmtDate(c.last_sync_at)}` : " · never synced"}
                  {c.last_status ? ` · ${c.last_status}` : ""}
                </span>
              </div>
              {can("ingest.write") && (
                <>
                  <button className="btn-ghost btn-sm" disabled={busy === c.id} onClick={() => sync(c.id)}>
                    {busy === c.id ? "…" : <><IconRefresh width={15} height={15} /> Sync</>}
                  </button>
                  <button className="btn-danger btn-sm" onClick={() => remove(c.id)}>Remove</button>
                </>
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
  const providers = useFetch<Provider[]>(() => api.get("/providers"), []);
  const connections = useFetch<any[]>(() => api.get("/connections"), []);
  const [rebuilding, setRebuilding] = useState(false);

  async function rebuild() {
    setRebuilding(true);
    try {
      await api.post("/ingest/rebuild-agg");
      toast("Aggregates rebuilt");
    } catch { toast("Rebuild failed", "err"); }
    finally { setRebuilding(false); }
  }

  if (providers.loading) return <Loading />;

  return (
    <>
      <h1 className="large-title" style={{ marginBottom: 16 }}>Imports &amp; sync</h1>
      <div className="col" style={{ gap: 20 }}>
        <FileImport providers={providers.data || []} onDone={() => connections.reload()} />
        <Connections providers={providers.data || []} connections={connections.data || []} reload={connections.reload} />

        {can("settings.manage") && (
          <div className="card">
            <div className="row">
              <div className="col" style={{ gap: 2, flex: 1 }}>
                <span className="headline">Maintenance</span>
                <span className="caption">Recompute the precomputed daily aggregates from raw events.</span>
              </div>
              <button className="btn-ghost btn-sm" disabled={rebuilding} onClick={rebuild}>
                {rebuilding ? "…" : <><IconCheck width={16} height={16} /> Rebuild aggregates</>}
              </button>
            </div>
          </div>
        )}
      </div>
    </>
  );
}
