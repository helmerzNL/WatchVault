import { useState } from "react";
import { Link } from "react-router-dom";
import { useApp } from "../lib/app";
import { useT, providerLabel } from "../lib/i18n";
import { api, ApiError } from "../lib/api";
import { useFetch } from "../lib/useFetch";
import { Section } from "../components/ui";
import { IconFilm, IconTv, IconClose, IconChevron } from "../components/icons";
import { TagPill } from "../components/TagChips";
import { ACCENTS, fmtDate } from "../lib/format";

function Appearance() {
  const { prefs, savePrefs, profiles, user, can } = useApp();
  const { t } = useT();
  const ownId = profiles.find((p) => p.id === user?.id)?.id;
  const defaultProfile = prefs.default_profile || ownId || "all";
  const cinemaOn = prefs.cinemaAdd !== false;
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
        <div>
          <label>{t("settings.defaultProfile")}</label>
          <div className="row" style={{ gap: 12, alignItems: "center" }}>
            <select value={defaultProfile} onChange={(e) => savePrefs({ default_profile: e.target.value })}
              style={{ width: "auto", minWidth: 180 }}>
              <option value="all">{t("common.household")}</option>
              {profiles.map((p) => (
                <option key={p.id} value={p.id}>{p.display_name}</option>
              ))}
            </select>
            <span className="caption" style={{ flex: 1 }}>{t("settings.defaultProfileHint")}</span>
          </div>
        </div>
        {can("ingest.write") && (
          <div>
            <label>{t("cinema.add")}</label>
            <div className="row" style={{ gap: 12, alignItems: "center" }}>
              <div className="seg">
                <button className={cinemaOn ? "active" : ""} onClick={() => savePrefs({ cinemaAdd: true })}>{t("common.on")}</button>
                <button className={!cinemaOn ? "active" : ""} onClick={() => savePrefs({ cinemaAdd: false })}>{t("common.off")}</button>
              </div>
              <span className="caption" style={{ flex: 1 }}>{t("cinema.toggleHint")}</span>
            </div>
          </div>
        )}
        <div>
          <label>{t("settings.expert")}</label>
          <div className="row" style={{ gap: 12, alignItems: "center" }}>
            <div className="seg">
              <button className={prefs.expert ? "active" : ""} onClick={() => savePrefs({ expert: true })}>{t("common.on")}</button>
              <button className={!prefs.expert ? "active" : ""} onClick={() => savePrefs({ expert: false })}>{t("common.off")}</button>
            </div>
            <span className="caption" style={{ flex: 1 }}>{t("settings.expertHint")}</span>
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

function Plugins({ bare }: { bare?: boolean } = {}) {
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
    <Section title={bare ? "" : t("settings.plugins")} bare={bare}>
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

function Account() {
  const { user, logout } = useApp();
  const { t } = useT();
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
          <button className="btn-danger" onClick={logout}>{t("settings.signOut")}</button>
        </div>
      </div>
    </Section>
  );
}

function AttributionLog({ embedded }: { embedded?: boolean } = {}) {
  const { can, toast, prefs } = useApp();
  const { t } = useT();
  const [open, setOpen] = useState(!!embedded);
  const [filter, setFilter] = useState<"all" | "other">("other");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [history, setHistory] = useState<Record<string, any[]>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(() => new Set());
  const [bulkProvider, setBulkProvider] = useState("");
  const log = useFetch<any>(() => api.get("/attribution-log", { filter }), [filter]);
  const provs = useFetch<any[]>(() => api.get("/providers"), []);
  if (!can("ingest.write") || !prefs.expert) return null;

  async function toggleHistory(titleId: string) {
    if (expanded === titleId) { setExpanded(null); return; }
    setExpanded(titleId);
    if (!history[titleId]) {
      try {
        const res = await api.get(`/attribution-log/${titleId}/history`);
        setHistory((h) => ({ ...h, [titleId]: res.items || [] }));
      } catch { /* ignore */ }
    }
  }

  async function reattribute(titleId: string) {
    setBusy(titleId);
    try {
      await api.post(`/attribution-log/${titleId}/reattribute`);
      toast(t("attrib.reattributed"));
      setHistory((h) => { const n = { ...h }; delete n[titleId]; return n; });
      log.reload();
    } catch (e) { toast(e instanceof ApiError ? e.message : t("settings.failed"), "err"); }
    finally { setBusy(null); }
  }

  async function reattributeAll() {
    setBusy("__all__");
    try { await api.post("/attribution-log/reattribute-all"); toast(t("attrib.queued")); }
    catch (e) { toast(e instanceof ApiError ? e.message : t("settings.failed"), "err"); }
    finally { setBusy(null); }
  }

  const items: any[] = log.data?.items || [];

  function toggleSelect(id: string) {
    setSelected((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  }
  function toggleSelectAll() {
    setSelected((s) => {
      const allSelected = items.length > 0 && items.every((it) => s.has(it.title_id));
      return allSelected ? new Set() : new Set(items.map((it) => it.title_id));
    });
  }

  // Fold Plex + Jellyfin into one "Digital Library" option for the bulk picker.
  const provOptions: any[] = [];
  let digitalSeen = false;
  for (const p of provs.data || []) {
    if (p.key === "plex" || p.key === "jellyfin") {
      if (digitalSeen) continue;
      digitalSeen = true;
      provOptions.push({ ...p, key: "digital_library" });
    } else provOptions.push(p);
  }

  async function bulkApply() {
    if (selected.size === 0) return;
    setBusy("__bulk__");
    try {
      const res = await api.post("/attribution-log/bulk-platform", {
        title_ids: [...selected], provider_id: bulkProvider || null,
      });
      toast(t("attrib.bulkDone", { n: res.updated ?? selected.size }));
      setSelected(new Set());
      setBulkProvider("");
      log.reload();
    } catch (e) { toast(e instanceof ApiError ? e.message : t("settings.failed"), "err"); }
    finally { setBusy(null); }
  }

  const allSelected = items.length > 0 && items.every((it) => selected.has(it.title_id));

  return (
    <Section title={t("attrib.title")}
      right={embedded ? undefined : <button className="btn-ghost btn-sm" onClick={() => setOpen((o) => !o)}>
        {open ? t("common.collapse") : t("common.expand")}</button>}>
      {open && (
      <div className="card col" style={{ gap: 14 }}>
        <span className="caption">{t("attrib.help")}</span>
        <div className="row wrap" style={{ gap: 10, alignItems: "center" }}>
          <div className="seg">
            <button className={filter === "other" ? "active" : ""} onClick={() => setFilter("other")}>{t("attrib.filterOther")}</button>
            <button className={filter === "all" ? "active" : ""} onClick={() => setFilter("all")}>{t("attrib.filterAll")}</button>
          </div>
          <div className="spacer" style={{ flex: 1 }} />
          {log.data && <span className="caption">{t("attrib.summary", { other: log.data.other, total: log.data.total })}</span>}
          <button className="btn-ghost btn-sm" style={{ flexShrink: 0 }} disabled={busy === "__all__"} onClick={reattributeAll}>{t("attrib.reattributeAll")}</button>
        </div>

        {selected.size > 0 && (
          <div className="row wrap" style={{ gap: 10, alignItems: "center", padding: "10px 12px", background: "var(--accent-subtle)", borderRadius: 10 }}>
            <strong style={{ fontSize: "0.9rem" }}>{t("attrib.selectedCount", { n: selected.size })}</strong>
            <div className="spacer" style={{ flex: 1 }} />
            <select value={bulkProvider} onChange={(e) => setBulkProvider(e.target.value)} style={{ minHeight: 34, padding: "4px 8px" }}>
              <option value="">{t("title.platformAuto")}</option>
              {provOptions.map((p) => (
                <option key={p.id} value={p.id}>{providerLabel(t, p.key, p.name)}</option>
              ))}
            </select>
            <button className="btn btn-primary btn-sm" style={{ flexShrink: 0 }} disabled={busy === "__bulk__"} onClick={bulkApply}>{t("attrib.assign")}</button>
            <button className="btn-ghost btn-sm" style={{ flexShrink: 0 }} onClick={() => setSelected(new Set())}>{t("common.cancel")}</button>
          </div>
        )}

        {items.length > 0 && (
          <label className="row" style={{ gap: 8, alignItems: "center", cursor: "pointer" }}>
            <input type="checkbox" checked={allSelected} onChange={toggleSelectAll}
              style={{ width: 18, height: 18 }} />
            <span className="caption">{t("attrib.selectAll")}</span>
          </label>
        )}

        <div className="col" style={{ gap: 0 }}>
          {items.map((it) => (
            <div key={it.title_id} className="col" style={{ gap: 0 }}>
              <div className="list-row" style={{ flexWrap: "wrap", alignItems: "center", gap: 10 }}>
                <input type="checkbox" checked={selected.has(it.title_id)} onChange={() => toggleSelect(it.title_id)}
                  style={{ width: 18, height: 18, flexShrink: 0 }} />
                <Link to={`/title/${it.title_id}`} className="imp-thumb">
                  {it.poster
                    ? <img src={it.poster} alt="" loading="lazy" />
                    : <div className="imp-thumb-ph">{it.kind === "movie" ? <IconFilm width={18} height={18} /> : <IconTv width={18} height={18} />}</div>}
                </Link>
                <div className="col" style={{ flex: 1, gap: 2, minWidth: 160 }}>
                  <Link to={`/title/${it.title_id}`} style={{ fontWeight: 600 }}>{it.title}</Link>
                  <span className="caption">
                    {it.kind === "movie" ? t("common.film") : t("common.series")} · {t(`attrib.reason.${it.reason}`)}
                  </span>
                  {it.networks.length > 0 && (
                    <span className="caption">{t("attrib.networks")}: {it.networks.join(", ")}</span>
                  )}
                </div>
                <span className="chip" style={{ minHeight: 0, padding: "2px 10px", background: it.provider_color || "var(--accent)", color: "#fff" }}>
                  {providerLabel(t, it.provider_key, it.provider_name || it.provider_key || "")}
                </span>
                <button className="btn-ghost btn-sm" style={{ flexShrink: 0 }} onClick={() => toggleHistory(it.title_id)}>{t("attrib.history")}</button>
                <button className="btn-ghost btn-sm" style={{ flexShrink: 0 }} disabled={busy === it.title_id} onClick={() => reattribute(it.title_id)}>{t("attrib.reattribute")}</button>
              </div>
              {expanded === it.title_id && (
                <div className="col" style={{ gap: 4, padding: "4px 0 12px 12px" }}>
                  {(history[it.title_id] || []).map((h: any, i: number) => (
                    <span key={i} className="caption">
                      {fmtDate(h.created_at)} · {providerLabel(t, h.provider_key, h.provider_key || "—")} · {t(`attrib.reason.${h.reason}`)}
                      {h.moved ? ` · ${t("attrib.moved", { n: h.moved })}` : ""}
                    </span>
                  ))}
                  {(history[it.title_id] || []).length === 0 && <span className="caption muted">—</span>}
                </div>
              )}
            </div>
          ))}
          {log.data && items.length === 0 && <p className="muted">{t("attrib.empty")}</p>}
        </div>
      </div>
      )}
    </Section>
  );
}

function DangerZone() {
  const { can, toast } = useApp();
  const { t } = useT();
  const [confirmText, setConfirmText] = useState("");
  const [busy, setBusy] = useState(false);
  if (!can("settings.manage")) return null;

  const word = t("settings.resetConfirmWord");
  const armed = confirmText.trim().toUpperCase() === word.toUpperCase();

  async function reset() {
    if (!armed) return;
    if (!confirm(t("settings.resetFinalConfirm"))) return;
    setBusy(true);
    try {
      const res = await api.post("/ingest/reset-all", { confirm: true });
      const r = res.removed || {};
      toast(t("settings.resetDone", {
        events: r.events ?? 0, titles: r.titles ?? 0, people: r.people ?? 0,
      }));
      setTimeout(() => window.location.reload(), 1200);
    } catch (e) {
      toast(e instanceof ApiError ? e.message : t("settings.failed"), "err");
    } finally { setBusy(false); }
  }

  return (
    <Section title={t("settings.dangerZone")}>
      <div className="card col" style={{ gap: 14, borderColor: "var(--danger, #d4453a)" }}>
        <div className="col" style={{ gap: 4 }}>
          <strong>{t("settings.resetAll")}</strong>
          <span className="caption">{t("settings.resetAllHelp")}</span>
        </div>
        <div className="row wrap" style={{ gap: 10 }}>
          <input value={confirmText} onChange={(e) => setConfirmText(e.target.value)}
            placeholder={t("settings.resetConfirmPlaceholder", { word })} />
          <button className="btn-danger" style={{ flexShrink: 0 }} disabled={!armed || busy} onClick={reset}>
            {busy ? t("common.saving") : t("settings.resetAll")}
          </button>
        </div>
      </div>
    </Section>
  );
}

function ScrobbleSettings({ bare }: { bare?: boolean } = {}) {
  const { prefs, can, toast } = useApp();
  const { t } = useT();
  const profiles = useFetch<any[]>(() => api.get("/profiles"), []);
  const accountMap = useFetch<{ mappings: any[]; unmapped: any[] }>(() => api.get("/scrobble/account-map"), []);
  const settings = useFetch<{ commit_threshold: number }>(() => api.get("/scrobble/settings"), []);
  const [token, setToken] = useState<string | null>(null);
  const [threshold, setThreshold] = useState<string>("");
  const [savingT, setSavingT] = useState(false);

  if (!can("ingest.write") || !prefs.expert) return null;

  const origin = window.location.origin;
  const plexUrl = token ? `${origin}/api/scrobble/plex?token=${token}` : "";
  const genericUrl = `${origin}/api/scrobble/generic`;

  async function generate() {
    try {
      const res = await api.post("/tokens", { name: "Live scrobbling" });
      setToken(res.token);
    } catch { toast(t("settings.failed"), "err"); }
  }
  function copy(text: string) {
    navigator.clipboard?.writeText(text);
    toast(t("scrobble.copied"), "ok");
  }
  async function map(source: string, account_label: string, user_id: string) {
    try {
      await api.put("/scrobble/account-map", { source, account_label, user_id });
      accountMap.reload();
    } catch { toast(t("settings.failed"), "err"); }
  }
  async function saveThreshold() {
    setSavingT(true);
    try {
      const res = await api.put("/scrobble/settings", { commit_threshold: Number(threshold) });
      setThreshold(String(res.commit_threshold));
      toast(t("settings.saved"), "ok");
    } catch { toast(t("settings.failed"), "err"); }
    finally { setSavingT(false); }
  }

  const currentThreshold = threshold !== "" ? threshold : (settings.data ? String(settings.data.commit_threshold) : "");
  const rows: { source: string; account_label: string; user_id: string | null }[] = [
    ...(accountMap.data?.mappings || []).map((m) => ({ source: m.source, account_label: m.account_label, user_id: m.user_id })),
    ...(accountMap.data?.unmapped || []).map((u) => ({ source: u.source, account_label: u.account_label, user_id: null })),
  ];

  return (
    <Section title={bare ? "" : t("scrobble.title")} bare={bare}>
      <div className="card col" style={{ gap: 18 }}>
        <p className="caption">{t("scrobble.help")}</p>

        {token ? (
          <div className="card col" style={{ gap: 12, borderColor: "var(--accent)", background: "var(--bg)" }}>
            <span className="caption">{t("scrobble.tokenWarn")}</span>
            <div className="col" style={{ gap: 4 }}>
              <label>{t("scrobble.plexUrl")}</label>
              <div className="row" style={{ gap: 8 }}>
                <div className="code-box" style={{ flex: 1, wordBreak: "break-all" }}>{plexUrl}</div>
                <button className="btn-ghost btn-sm" style={{ flexShrink: 0 }} onClick={() => copy(plexUrl)}>{t("scrobble.copy")}</button>
              </div>
            </div>
            <div className="col" style={{ gap: 4 }}>
              <label>{t("scrobble.genericUrl")}</label>
              <div className="row" style={{ gap: 8 }}>
                <div className="code-box" style={{ flex: 1, wordBreak: "break-all" }}>{genericUrl}</div>
                <button className="btn-ghost btn-sm" style={{ flexShrink: 0 }} onClick={() => copy(genericUrl)}>{t("scrobble.copy")}</button>
              </div>
            </div>
            <div className="col" style={{ gap: 4 }}>
              <label>{t("scrobble.bearer")}</label>
              <div className="row" style={{ gap: 8 }}>
                <div className="code-box" style={{ flex: 1, wordBreak: "break-all" }}>Bearer {token}</div>
                <button className="btn-ghost btn-sm" style={{ flexShrink: 0 }} onClick={() => copy(`Bearer ${token}`)}>{t("scrobble.copy")}</button>
              </div>
            </div>
            <p className="caption">{t("scrobble.setupHint")}</p>
            <button className="btn-ghost btn-sm" style={{ alignSelf: "flex-start" }} onClick={() => setToken(null)}>{t("scrobble.done")}</button>
          </div>
        ) : (
          <div className="col" style={{ gap: 8 }}>
            <button className="btn-ghost" style={{ alignSelf: "flex-start" }} onClick={generate}>{t("scrobble.generate")}</button>
            <p className="caption">{t("scrobble.setupHint")}</p>
          </div>
        )}

        <div className="col" style={{ gap: 8 }}>
          <label>{t("scrobble.mapping")}</label>
          <p className="caption">{t("scrobble.mappingHelp")}</p>
          {rows.length === 0 ? <p className="muted">{t("scrobble.noAccounts")}</p> : rows.map((r) => (
            <div key={`${r.source}:${r.account_label}`} className="list-row">
              <div className="col" style={{ flex: 1, gap: 2 }}>
                <strong>{r.account_label}</strong>
                <span className="caption">{providerLabel(t, r.source, r.source)}</span>
              </div>
              <select value={r.user_id || ""} onChange={(e) => map(r.source, r.account_label, e.target.value)}
                style={{ width: "auto", minWidth: 160 }}>
                <option value="">{t("scrobble.unmapped")}</option>
                {(profiles.data || []).map((p) => (
                  <option key={p.id} value={p.id}>{p.display_name}</option>
                ))}
              </select>
            </div>
          ))}
        </div>

        {can("settings.manage") && (
          <div className="col" style={{ gap: 6 }}>
            <label>{t("scrobble.threshold")}</label>
            <div className="row" style={{ gap: 10, alignItems: "center" }}>
              <input type="number" min={1} max={100} value={currentThreshold}
                onChange={(e) => setThreshold(e.target.value)} style={{ width: 100 }} />
              <span className="caption">%</span>
              <button className="btn-ghost btn-sm" disabled={savingT || currentThreshold === ""} onClick={saveThreshold}>
                {savingT ? "…" : t("common.save")}
              </button>
            </div>
            <p className="caption">{t("scrobble.thresholdHelp")}</p>
          </div>
        )}
      </div>
    </Section>
  );
}

function TagManager() {
  const { can, toast } = useApp();
  const { t } = useT();
  const tags = useFetch<any[]>(() => api.get("/tags"), []);
  const [name, setName] = useState("");
  const [color, setColor] = useState<string>(ACCENTS[0]?.value || "");
  const [busy, setBusy] = useState(false);
  const canView = can("catalog.read");
  const canEdit = can("ingest.write");
  if (!canView) return null;

  async function create() {
    const n = name.trim();
    if (!n) return;
    setBusy(true);
    try {
      await api.post("/tags", { name: n, color: color || null });
      setName("");
      tags.reload();
    } catch (e) { toast(e instanceof ApiError ? e.message : t("settings.failed"), "err"); }
    finally { setBusy(false); }
  }

  async function remove(id: string, uses: number) {
    if (uses > 0 && !confirm(t("tags.deleteConfirm", { n: uses }))) return;
    try { await api.del(`/tags/${id}`); tags.reload(); }
    catch (e) { toast(e instanceof ApiError ? e.message : t("settings.failed"), "err"); }
  }

  const list = tags.data || [];
  return (
    <div className="card col" style={{ gap: 14 }}>
      <p className="caption" style={{ margin: 0 }}>{t("tags.manageHelp")}</p>
      {canEdit && (
        <div className="row wrap" style={{ gap: 10, alignItems: "center" }}>
          <input value={name} onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") create(); }}
            placeholder={t("tags.newPlaceholder")} style={{ flex: 1, minWidth: 160 }} />
          <div className="swatches" style={{ gap: 6 }}>
            {ACCENTS.map((a) => (
              <span key={a.value} className={`swatch ${color === a.value ? "active" : ""}`}
                style={{ background: a.value }} title={a.name} onClick={() => setColor(a.value)} />
            ))}
          </div>
          <button className="btn-primary" style={{ flexShrink: 0 }} disabled={busy || !name.trim()} onClick={create}>
            {t("tags.create")}
          </button>
        </div>
      )}
      {list.length === 0 ? (
        <p className="muted" style={{ margin: 0 }}>{t("tags.none")}</p>
      ) : (
        <div className="col" style={{ gap: 8 }}>
          {list.map((tg) => (
            <div key={tg.id} className="list-row" style={{ alignItems: "center", gap: 10 }}>
              <TagPill tag={tg} />
              <span className="caption" style={{ flex: 1 }}>{t("tags.uses", { n: tg.uses })}</span>
              {canEdit && (
                <button className="manual-x" title={t("common.remove")} aria-label={t("common.remove")}
                  onClick={() => remove(tg.id, tg.uses)}>
                  <IconClose width={14} height={14} />
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function Accordion({ title, children, defaultOpen }: { title: string; children: React.ReactNode; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(!!defaultOpen);
  return (
    <div className="accordion card" style={{ padding: 0, overflow: "hidden" }}>
      <button className="accordion-head row" onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        style={{ width: "100%", justifyContent: "space-between", alignItems: "center", gap: 10,
          padding: "14px 16px", background: "transparent", border: "none", cursor: "pointer" }}>
        <strong>{title}</strong>
        <IconChevron width={16} height={16} style={{ transform: open ? "rotate(90deg)" : "none", transition: "transform .15s" }} />
      </button>
      {open && <div className="accordion-body" style={{ padding: "0 16px 16px" }}>{children}</div>}
    </div>
  );
}

type Tab = "display" | "settings" | "logs" | "profile";

export function Settings() {
  const { t } = useT();
  const { can, prefs } = useApp();
  const [tab, setTab] = useState<Tab>(() => {
    const q = new URLSearchParams(window.location.search).get("tab");
    return (["display", "settings", "logs", "profile"].includes(q || "") ? q : "display") as Tab;
  });

  function pick(next: Tab) {
    setTab(next);
    const url = new URL(window.location.href);
    url.searchParams.set("tab", next);
    window.history.replaceState(null, "", url.toString());
  }

  const tabs: { id: Tab; label: string }[] = [
    { id: "display", label: t("settings.tabs.display") },
    { id: "settings", label: t("settings.tabs.settings") },
    { id: "logs", label: t("settings.tabs.logs") },
    { id: "profile", label: t("settings.tabs.profile") },
  ];

  const showScrobble = can("ingest.write") && prefs.expert;
  const showPlugins = can("plugins.manage");
  const showTags = can("catalog.read");

  return (
    <>
      <h1 className="large-title" style={{ marginBottom: 12 }}>{t("settings.title")}</h1>
      <div className="seg settings-pills" style={{ marginBottom: 18 }}>
        {tabs.map((tb) => (
          <button key={tb.id} className={tab === tb.id ? "active" : ""} onClick={() => pick(tb.id)}>{tb.label}</button>
        ))}
      </div>

      {tab === "display" && <Appearance />}

      {tab === "settings" && (
        <div className="col" style={{ gap: 12 }}>
          {showScrobble && <Accordion title={t("scrobble.title")} defaultOpen><ScrobbleSettings bare /></Accordion>}
          {showPlugins && <Accordion title={t("settings.plugins")}><Plugins bare /></Accordion>}
          {showTags && <Accordion title={t("settings.tags")} defaultOpen={!showScrobble}><TagManager /></Accordion>}
          {!showScrobble && !showPlugins && !showTags && <p className="muted">{t("settings.emptyTab")}</p>}
        </div>
      )}

      {tab === "logs" && <AttributionLog embedded />}

      {tab === "profile" && (
        <>
          <Account />
          <Household />
          <DangerZone />
        </>
      )}
    </>
  );
}
