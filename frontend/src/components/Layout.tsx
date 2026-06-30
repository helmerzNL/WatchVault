import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useApp } from "../lib/app";
import { useT } from "../lib/i18n";
import { LanguagePicker } from "./LanguagePicker";
import { Dropdown } from "./Menu";
import { initials } from "../lib/format";
import {
  IconChart, IconChevron, IconHome, IconImport, IconLogo, IconSearch, IconSettings, IconUsers,
} from "./icons";

function ProfileSwitcher() {
  const { profiles, scope, setScope, user } = useApp();
  const { t } = useT();
  const navigate = useNavigate();
  const current = scope === "all" ? null : profiles.find((p) => p.id === scope);
  const label = current ? current.display_name : t("common.household");

  return (
    <Dropdown
      align="right"
      minWidth={220}
      buttonClassName="btn-ghost btn-sm"
      button={() => (
        <>
          <span className="avatar" style={{ width: 24, height: 24, fontSize: 11 }}>
            {current?.avatar ? <img src={current.avatar} alt="" /> : current ? initials(current.display_name) : "★"}
          </span>
          <span style={{ maxWidth: 110, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{label}</span>
          <IconChevron width={16} height={16} style={{ transform: "rotate(90deg)" }} />
        </>
      )}
    >
      {(close) => (
        <>
          <button className="menu-row" data-active={scope === "all"} onClick={() => { setScope("all"); close(); }}>
            <span className="avatar" style={{ width: 30, height: 30, fontSize: 13 }}>★</span>
            <span className="col" style={{ gap: 0, alignItems: "flex-start" }}>
              <strong>{t("common.household")}</strong>
              <span className="caption">{t("common.everyoneCombined")}</span>
            </span>
          </button>
          {profiles.map((p) => (
            <button key={p.id} className="menu-row" data-active={scope === p.id}
              onClick={() => { setScope(p.id); close(); }}>
              <span className="avatar" style={{ width: 30, height: 30, fontSize: 13 }}>
                {p.avatar ? <img src={p.avatar} alt="" /> : initials(p.display_name)}
              </span>
              <span className="col" style={{ gap: 0, alignItems: "flex-start" }}>
                <strong>{p.display_name}{p.id === user?.id ? ` (${t("common.you")})` : ""}</strong>
                <span className="caption">{p.events} {t("common.events")}</span>
              </span>
            </button>
          ))}
          <div className="menu-divider" />
          <button className="menu-row" onClick={() => { navigate("/settings"); close(); }}>
            <span className="avatar" style={{ width: 30, height: 30, background: "var(--accent-subtle)", color: "var(--accent)" }}>
              <IconSettings width={18} height={18} />
            </span>
            <span className="col" style={{ gap: 0, alignItems: "flex-start" }}>
              <strong>{t("nav.settings")}</strong>
            </span>
          </button>
        </>
      )}
    </Dropdown>
  );
}

const NAV = [
  { to: "/", key: "nav.dashboard", icon: IconHome, end: true },
  { to: "/overviews", key: "nav.overviews", icon: IconChart },
  { to: "/search", key: "nav.search", icon: IconSearch },
  { to: "/imports", key: "nav.imports", icon: IconImport },
  { to: "/profiles", key: "nav.profiles", icon: IconUsers },
];

export function Layout() {
  const loc = useLocation();
  const { t } = useT();
  return (
    <div className="app-shell">
      <header className="topbar glass">
        <Link to="/" className="brand">
          <IconLogo size={28} />
          <span>WatchVault</span>
        </Link>
        <nav className="nav-links">
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.end}
              className={({ isActive }) => (isActive ? "active" : "")}>{t(n.key)}</NavLink>
          ))}
        </nav>
        <div className="spacer" />
        <LanguagePicker />
        <ProfileSwitcher />
      </header>

      <main className="app-main" key={loc.pathname}>
        <Outlet />
      </main>

      <nav className="tabbar glass">
        {NAV.map((n) => {
          const Icon = n.icon;
          return (
            <NavLink key={n.to} to={n.to} end={n.end} className={({ isActive }) => (isActive ? "active" : "")}>
              <Icon />
              <span>{t(n.key)}</span>
            </NavLink>
          );
        })}
      </nav>
    </div>
  );
}
