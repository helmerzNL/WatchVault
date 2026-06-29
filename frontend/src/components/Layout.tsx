import { useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import { useApp } from "../lib/app";
import { initials } from "../lib/format";
import {
  IconChart, IconChevron, IconHome, IconImport, IconSearch, IconSettings, IconUsers,
} from "./icons";

function ProfileSwitcher() {
  const { profiles, scope, setScope, user } = useApp();
  const [open, setOpen] = useState(false);
  const current = scope === "all" ? null : profiles.find((p) => p.id === scope);
  const label = current ? current.display_name : "Household";

  return (
    <div style={{ position: "relative" }}>
      <button className="btn-ghost btn-sm" onClick={() => setOpen((o) => !o)} aria-haspopup="listbox" aria-expanded={open}>
        <span className="avatar" style={{ width: 24, height: 24, fontSize: 11 }}>
          {current?.avatar ? <img src={current.avatar} alt="" /> : current ? initials(current.display_name) : "★"}
        </span>
        <span style={{ maxWidth: 110, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{label}</span>
        <IconChevron width={16} height={16} style={{ transform: "rotate(90deg)" }} />
      </button>
      {open && (
        <>
          <div style={{ position: "fixed", inset: 0, zIndex: 90 }} onClick={() => setOpen(false)} />
          <div className="glass" style={{
            position: "absolute", right: 0, top: "calc(100% + 8px)", zIndex: 100,
            minWidth: 220, padding: 8, borderRadius: 16,
          }} role="listbox">
            <button className="menu-row" data-active={scope === "all"} onClick={() => { setScope("all"); setOpen(false); }}>
              <span className="avatar" style={{ width: 30, height: 30, fontSize: 13 }}>★</span>
              <span className="col" style={{ gap: 0, alignItems: "flex-start" }}>
                <strong>Household</strong>
                <span className="caption">Everyone combined</span>
              </span>
            </button>
            {profiles.map((p) => (
              <button key={p.id} className="menu-row" data-active={scope === p.id}
                onClick={() => { setScope(p.id); setOpen(false); }}>
                <span className="avatar" style={{ width: 30, height: 30, fontSize: 13 }}>
                  {p.avatar ? <img src={p.avatar} alt="" /> : initials(p.display_name)}
                </span>
                <span className="col" style={{ gap: 0, alignItems: "flex-start" }}>
                  <strong>{p.display_name}{p.id === user?.id ? " (you)" : ""}</strong>
                  <span className="caption">{p.events} events</span>
                </span>
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

const NAV = [
  { to: "/", label: "Dashboard", icon: IconHome, end: true },
  { to: "/overviews", label: "Overviews", icon: IconChart },
  { to: "/search", label: "Search", icon: IconSearch },
  { to: "/imports", label: "Imports", icon: IconImport },
  { to: "/profiles", label: "Profiles", icon: IconUsers },
  { to: "/settings", label: "Settings", icon: IconSettings },
];

export function Layout() {
  const loc = useLocation();
  return (
    <div className="app-shell">
      <header className="topbar glass">
        <Link to="/" className="brand">
          <img src="/favicon.svg" alt="" />
          <span>WatchVault</span>
        </Link>
        <nav className="nav-links">
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.end}
              className={({ isActive }) => (isActive ? "active" : "")}>{n.label}</NavLink>
          ))}
        </nav>
        <div className="spacer" />
        <ProfileSwitcher />
      </header>

      <main className="app-main" key={loc.pathname}>
        <Outlet />
      </main>

      <nav className="tabbar glass">
        {NAV.filter((n) => n.to !== "/settings").map((n) => {
          const Icon = n.icon;
          return (
            <NavLink key={n.to} to={n.to} end={n.end} className={({ isActive }) => (isActive ? "active" : "")}>
              <Icon />
              <span>{n.label}</span>
            </NavLink>
          );
        })}
      </nav>
    </div>
  );
}
