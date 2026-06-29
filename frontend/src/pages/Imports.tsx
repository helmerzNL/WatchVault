import { useMemo, useRef, useState } from "react";
import { useApp } from "../lib/app";
import { api, ApiError } from "../lib/api";
import { useFetch } from "../lib/useFetch";
import { Loading, Section } from "../components/ui";
import { IconImport, IconRefresh, IconPlus, IconCheck } from "../components/icons";
import { fmtDate } from "../lib/format";

interface Provider {
  id: string; key: string; name: string; ingest_type: string; adapter: string; color?: string;
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
  const [baseUrl, setBaseUrl] = useState("");
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState<string | null>(null);

  async function create() {
    setBusy("create");
    try {
      await api.post("/connections", {
        provider, name: name || undefined,
        config: { base_url: baseUrl, token },
      });
      toast("Connection added");
      setAdding(false); setName(""); setBaseUrl(""); setToken("");
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
        Plex & Jellyfin expose official APIs — connect once and sync watch history on demand.
      </p>

      {adding && (
        <div className="card" style={{ marginBottom: 16, background: "var(--bg)" }}>
          <div className="filters-grid" style={{ marginBottom: 12 }}>
            <div>
              <label>Service</label>
              <select value={provider} onChange={(e) => setProvider(e.target.value)}>
                {apiProviders.map((p) => <option key={p.key} value={p.key}>{p.name}</option>)}
              </select>
            </div>
            <div>
              <label>Name</label>
              <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Living room Plex" />
            </div>
          </div>
          <div style={{ marginBottom: 12 }}>
            <label>Server URL</label>
            <input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="http://192.168.1.10:32400" />
          </div>
          <div style={{ marginBottom: 12 }}>
            <label>API token</label>
            <input value={token} onChange={(e) => setToken(e.target.value)} placeholder="X-Plex-Token / Jellyfin API key" type="password" />
          </div>
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
