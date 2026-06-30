import {
  createContext, useCallback, useContext, useEffect, useMemo, useRef, useState,
  type ReactNode,
} from "react";
import { api } from "./api";
import { applyBrandIcons } from "./branding";

export interface User {
  id: string;
  display_name: string;
  email?: string | null;
  avatar_path?: string | null;
  accent_color?: string | null;
  is_admin: boolean;
  household_id: string;
  household_name?: string | null;
  permissions: string[];
}

export interface Prefs {
  theme: "light" | "dark" | "system";
  accent: string;
  default_profile: string;
  language: string;
  [k: string]: any;
}

export interface Profile {
  id: string;
  display_name: string;
  avatar?: string | null;
  accent_color?: string | null;
  is_admin: boolean;
  events: number;
  last_seen_at?: string | null;
}

interface Toast { kind: "ok" | "err"; msg: string; }

interface AppCtx {
  ready: boolean;
  bootstrapped: boolean;
  user: User | null;
  prefs: Prefs;
  profiles: Profile[];
  scope: string; // 'all' or a user id
  setScope: (s: string) => void;
  refreshAuth: () => Promise<void>;
  refreshProfiles: () => Promise<void>;
  savePrefs: (patch: Partial<Prefs>) => Promise<void>;
  logout: () => Promise<void>;
  toast: (msg: string, kind?: "ok" | "err") => void;
  can: (perm: string) => boolean;
}

const DEFAULT_PREFS: Prefs = { theme: "system", accent: "#0a84ff", default_profile: "all", language: "en" };

const Ctx = createContext<AppCtx>(null as any);
export const useApp = () => useContext(Ctx);

function applyTheme(prefs: Prefs) {
  const root = document.documentElement;
  if (prefs.theme === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", prefs.theme);
  if (prefs.accent) {
    root.style.setProperty("--accent", prefs.accent);
    applyBrandIcons(prefs.accent);
  }
}

export function AppProvider({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [bootstrapped, setBootstrapped] = useState(true);
  const [user, setUser] = useState<User | null>(null);
  const [prefs, setPrefs] = useState<Prefs>(DEFAULT_PREFS);
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [scope, setScope] = useState("all");
  const [toastState, setToastState] = useState<Toast | null>(null);
  const toastTimer = useRef<number>();

  const toast = useCallback((msg: string, kind: "ok" | "err" = "ok") => {
    setToastState({ kind, msg });
    window.clearTimeout(toastTimer.current);
    toastTimer.current = window.setTimeout(() => setToastState(null), 3200);
  }, []);

  const refreshAuth = useCallback(async () => {
    const status = await api.get("/auth/status");
    setBootstrapped(status.bootstrapped);
    setUser(status.user || null);
  }, []);

  const refreshProfiles = useCallback(async () => {
    try {
      const list = await api.get("/profiles");
      setProfiles(list);
    } catch {
      setProfiles([]);
    }
  }, []);

  const loadPrefs = useCallback(async () => {
    try {
      const p = await api.get("/preferences");
      const merged = { ...DEFAULT_PREFS, ...p };
      setPrefs(merged);
      applyTheme(merged);
      setScope((s) => (s === "all" ? merged.default_profile || "all" : s));
    } catch {
      /* keep defaults */
    }
  }, []);

  const savePrefs = useCallback(async (patch: Partial<Prefs>) => {
    const optimistic = { ...prefs, ...patch };
    setPrefs(optimistic);
    applyTheme(optimistic);
    const saved = await api.put("/preferences", patch);
    const merged = { ...DEFAULT_PREFS, ...saved };
    setPrefs(merged);
    applyTheme(merged);
  }, [prefs]);

  const logout = useCallback(async () => {
    await api.post("/auth/logout").catch(() => {});
    setUser(null);
    setProfiles([]);
    setScope("all");
  }, []);

  const can = useCallback(
    (perm: string) => !!user && (user.permissions.includes("*") || user.permissions.includes(perm)),
    [user]
  );

  // Initial boot
  useEffect(() => {
    (async () => {
      await refreshAuth();
      setReady(true);
    })();
  }, [refreshAuth]);

  // When user becomes available, load prefs + profiles
  useEffect(() => {
    if (user) {
      loadPrefs();
      refreshProfiles();
    }
  }, [user, loadPrefs, refreshProfiles]);

  // Re-apply system theme on OS change while in system mode
  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const fn = () => { if (prefs.theme === "system") applyTheme(prefs); };
    mq.addEventListener("change", fn);
    return () => mq.removeEventListener("change", fn);
  }, [prefs]);

  const value = useMemo<AppCtx>(() => ({
    ready, bootstrapped, user, prefs, profiles, scope, setScope,
    refreshAuth, refreshProfiles, savePrefs, logout, toast, can,
  }), [ready, bootstrapped, user, prefs, profiles, scope, refreshAuth, refreshProfiles, savePrefs, logout, toast, can]);

  return (
    <Ctx.Provider value={value}>
      {children}
      {toastState && <div className={`toast ${toastState.kind}`}>{toastState.msg}</div>}
    </Ctx.Provider>
  );
}
