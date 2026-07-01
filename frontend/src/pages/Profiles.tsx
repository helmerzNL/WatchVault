import { useState } from "react";
import { Link } from "react-router-dom";
import { useApp } from "../lib/app";
import { useT } from "../lib/i18n";
import { api, ApiError } from "../lib/api";
import { useFetch } from "../lib/useFetch";
import { Loading, ErrorState, Section } from "../components/ui";
import { IconPlus, IconUsers, IconSettings, IconChevron, IconPencil } from "../components/icons";
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
  const [form, setForm] = useState({ first_name: "", last_name: "", accent_color: "" });
  const [avatarFile, setAvatarFile] = useState<File | null>(null);
  const [avatarPreview, setAvatarPreview] = useState<string | null>(null);
  const [savingEdit, setSavingEdit] = useState(false);

  function openEdit(p: any) {
    if (editing === p.id) { closeEdit(); return; }
    setEditing(p.id);
    setForm({
      first_name: p.first_name || "",
      last_name: p.last_name || "",
      accent_color: p.accent_color || "",
    });
    setAvatarFile(null);
    setAvatarPreview(null);
  }

  function closeEdit() {
    setEditing(null);
    setAvatarFile(null);
    if (avatarPreview) URL.revokeObjectURL(avatarPreview);
    setAvatarPreview(null);
  }

  function pickAvatar(f: File | null) {
    if (!f) return;
    if (!["image/png", "image/jpeg", "image/webp"].includes(f.type)) {
      toast(t("profiles.photoInvalid"), "err"); return;
    }
    if (f.size > 8 * 1024 * 1024) {
      toast(t("profiles.photoTooLarge"), "err"); return;
    }
    if (avatarPreview) URL.revokeObjectURL(avatarPreview);
    setAvatarFile(f);
    setAvatarPreview(URL.createObjectURL(f));
  }

  async function saveEdit(id: string) {
    setSavingEdit(true);
    try {
      await api.patch(`/profiles/${id}`, {
        first_name: form.first_name.trim(),
        last_name: form.last_name.trim(),
        accent_color: form.accent_color || null,
      });
      if (avatarFile) {
        const fd = new FormData();
        fd.append("file", avatarFile);
        await api.upload(`/profiles/${id}/avatar`, fd);
      }
      toast(t("profiles.profileSaved"));
      closeEdit();
      profiles.reload(); refreshProfiles();
    } catch (e) {
      toast(e instanceof ApiError ? e.message : t("settings.failed"), "err");
    } finally { setSavingEdit(false); }
  }

  async function removePhoto(id: string) {
    try {
      await api.del(`/profiles/${id}/avatar`);
      setAvatarFile(null);
      if (avatarPreview) URL.revokeObjectURL(avatarPreview);
      setAvatarPreview(null);
      profiles.reload(); refreshProfiles();
    } catch (e) {
      toast(e instanceof ApiError ? e.message : t("settings.failed"), "err");
    }
  }

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
                <button className="btn-ghost btn-sm" onClick={() => openEdit(p)}
                  title={t("profiles.edit")} aria-label={t("profiles.edit")}>
                  <IconPencil width={16} height={16} />
                </button>
              )}
              {can("profiles.manage") && p.id !== user?.id && (
                <button className="btn-danger btn-sm" onClick={() => remove(p.id, p.display_name)}>{t("common.remove")}</button>
              )}
              {editing === p.id && (
                <div className="col" style={{ flexBasis: "100%", gap: 14, marginTop: 14 }}>
                  <div className="row" style={{ gap: 14, alignItems: "center" }}>
                    <span className="avatar" style={{ width: 64, height: 64, fontSize: "1.3rem", background: form.accent_color || p.accent_color || "var(--accent)" }}>
                      {avatarPreview ? <img src={avatarPreview} alt="" />
                        : p.avatar ? <img src={p.avatar} alt="" />
                        : initials(form.first_name || p.display_name)}
                    </span>
                    <div className="col" style={{ gap: 8 }}>
                      <label className="btn-ghost btn-sm" style={{ cursor: "pointer", display: "inline-flex", width: "fit-content" }}>
                        {t("profiles.changePhoto")}
                        <input type="file" accept="image/png,image/jpeg,image/webp" style={{ display: "none" }}
                          onChange={(e) => pickAvatar(e.target.files?.[0] || null)} />
                      </label>
                      {p.avatar && !avatarPreview && (
                        <button className="btn-ghost btn-sm" onClick={() => removePhoto(p.id)}>{t("profiles.removePhoto")}</button>
                      )}
                    </div>
                  </div>
                  <div className="row" style={{ gap: 12, flexWrap: "wrap" }}>
                    <div className="col" style={{ gap: 4, flex: "1 1 140px" }}>
                      <label>{t("profiles.firstName")}</label>
                      <input value={form.first_name} onChange={(e) => setForm((f) => ({ ...f, first_name: e.target.value }))} />
                    </div>
                    <div className="col" style={{ gap: 4, flex: "1 1 140px" }}>
                      <label>{t("profiles.lastName")}</label>
                      <input value={form.last_name} onChange={(e) => setForm((f) => ({ ...f, last_name: e.target.value }))} />
                    </div>
                  </div>
                  <div className="col" style={{ gap: 6 }}>
                    <label>{t("profiles.accent")}</label>
                    <div className="swatches">
                      {ACCENTS.map((a) => (
                        <span key={a.value} className={`swatch ${form.accent_color === a.value ? "active" : ""}`}
                          style={{ background: a.value }} title={a.name}
                          onClick={() => setForm((f) => ({ ...f, accent_color: a.value }))} />
                      ))}
                    </div>
                  </div>
                  <div className="row" style={{ gap: 8 }}>
                    <button className="btn-primary btn-sm" disabled={savingEdit} onClick={() => saveEdit(p.id)}>
                      {savingEdit ? "…" : t("profiles.saveProfile")}
                    </button>
                    <button className="btn-ghost btn-sm" onClick={closeEdit}>{t("common.cancel")}</button>
                  </div>
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
