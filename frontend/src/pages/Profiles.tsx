import { useState } from "react";
import { Link } from "react-router-dom";
import { useApp } from "../lib/app";
import { useT } from "../lib/i18n";
import { api, ApiError } from "../lib/api";
import { useFetch } from "../lib/useFetch";
import { Loading, ErrorState, Section } from "../components/ui";
import { IconPlus, IconUsers, IconSettings, IconChevron } from "../components/icons";
import { initials, fmtNum, fmtDate, ACCENTS } from "../lib/format";

export function Profiles() {
  const { user, can, toast, refreshProfiles } = useApp();
  const { t } = useT();
  const profiles = useFetch<any[]>(() => api.get("/profiles"), []);
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState("");
  const [isAdmin, setIsAdmin] = useState(false);
  const [newCode, setNewCode] = useState<{ name: string; code: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);

  async function add() {
    if (!name.trim()) return;
    setBusy(true);
    try {
      const res = await api.post("/profiles", { display_name: name.trim(), is_admin: isAdmin });
      setNewCode({ name: name.trim(), code: res.recovery_code });
      setName(""); setIsAdmin(false); setAdding(false);
      profiles.reload(); refreshProfiles();
    } catch (e) {
      toast(e instanceof ApiError ? e.message : t("settings.failed"), "err");
    } finally { setBusy(false); }
  }

  async function saveAccent(id: string, accent: string) {
    await api.patch(`/profiles/${id}`, { accent_color: accent });
    profiles.reload(); refreshProfiles();
    setEditing(null);
  }

  async function remove(id: string, dn: string) {
    if (!confirm(t("profiles.removeConfirm", { name: dn }))) return;
    try {
      await api.del(`/profiles/${id}`);
      toast(t("profiles.profileRemoved"));
      profiles.reload(); refreshProfiles();
    } catch (e) {
      toast(e instanceof ApiError ? e.message : t("settings.failed"), "err");
    }
  }

  if (profiles.loading) return <Loading />;
  if (profiles.error) return <ErrorState error={profiles.error} retry={profiles.reload} />;

  return (
    <>
      <Section title={t("profiles.householdMembers")}
        right={can("profiles.manage") ? (
          <button className="btn-ghost btn-sm" onClick={() => setAdding((a) => !a)}>
            <IconPlus width={16} height={16} /> {t("profiles.addMember")}
          </button>
        ) : undefined}>

        {newCode && (
          <div className="card" style={{ marginBottom: 16, borderColor: "var(--accent)" }}>
            <span className="headline">{t("profiles.recoveryCodeFor", { name: newCode.name })}</span>
            <p className="caption" style={{ margin: "8px 0 12px" }}>
              {t("profiles.shareCode", { name: newCode.name })}
            </p>
            <div className="code-box" style={{ marginBottom: 12 }}>{newCode.code}</div>
            <button className="btn-ghost btn-sm" onClick={() => { navigator.clipboard?.writeText(newCode.code); setNewCode(null); }}>
              {t("profiles.copyDismiss")}
            </button>
          </div>
        )}

        {adding && (
          <div className="card" style={{ marginBottom: 16 }}>
            <div style={{ marginBottom: 12 }}>
              <label>{t("profiles.name")}</label>
              <input value={name} onChange={(e) => setName(e.target.value)} autoFocus placeholder={t("profiles.memberNamePlaceholder")}
                onKeyDown={(e) => e.key === "Enter" && add()} />
            </div>
            <label className="row" style={{ gap: 8, cursor: "pointer", marginBottom: 14 }}>
              <input type="checkbox" checked={isAdmin} onChange={(e) => setIsAdmin(e.target.checked)}
                style={{ width: "auto", minHeight: 0 }} />
              <span>{t("profiles.makeAdmin")}</span>
            </label>
            <button className="btn-primary" disabled={busy} onClick={add}>
              {busy ? "…" : t("profiles.createProfile")}
            </button>
          </div>
        )}

        <div className="card">
          {profiles.data!.map((p) => (
            <div key={p.id} className="list-row">
              <span className="avatar" style={{ background: p.accent_color || "var(--accent)" }}>
                {p.avatar ? <img src={p.avatar} alt="" /> : initials(p.display_name)}
              </span>
              <div className="col" style={{ flex: 1, gap: 2 }}>
                <strong>{p.display_name}{p.id === user?.id ? ` (${t("common.you")})` : ""}
                  {p.is_admin && <span className="chip" style={{ minHeight: 0, padding: "1px 8px", marginLeft: 8, fontSize: "0.7rem" }}>{t("profiles.admin")}</span>}
                </strong>
                <span className="caption">
                  {t("profiles.eventsCount", { count: fmtNum(p.events) })}{p.last_seen_at ? ` · ${t("profiles.seen", { date: fmtDate(p.last_seen_at) })}` : ""}
                </span>
              </div>
              {(can("profiles.manage") || p.id === user?.id) && (
                <button className="btn-ghost btn-sm" onClick={() => setEditing(editing === p.id ? null : p.id)}>
                  {t("profiles.accent")}
                </button>
              )}
              {can("profiles.manage") && p.id !== user?.id && (
                <button className="btn-danger btn-sm" onClick={() => remove(p.id, p.display_name)}>{t("common.remove")}</button>
              )}
              {editing === p.id && (
                <div className="swatches" style={{ flexBasis: "100%", marginTop: 10 }}>
                  {ACCENTS.map((a) => (
                    <span key={a.value} className={`swatch ${p.accent_color === a.value ? "active" : ""}`}
                      style={{ background: a.value }} title={a.name} onClick={() => saveAccent(p.id, a.value)} />
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      </Section>

      <div className="card" style={{ marginTop: 20 }}>
        <div className="row">
          <IconUsers width={20} height={20} />
          <div className="col" style={{ gap: 2, flex: 1 }}>
            <span className="headline">{t("profiles.howMembersJoin")}</span>
            <span className="caption">
              {t("profiles.howMembersJoinHelp")}
            </span>
          </div>
        </div>
      </div>

      <Link to="/settings" className="card nav-card mobile-only" style={{ marginTop: 20 }}>
        <div className="row">
          <IconSettings width={20} height={20} />
          <div className="col" style={{ gap: 2, flex: 1 }}>
            <span className="headline">{t("nav.settings")}</span>
            <span className="caption">{t("profiles.openSettingsHelp")}</span>
          </div>
          <IconChevron width={18} height={18} />
        </div>
      </Link>
    </>
  );
}
