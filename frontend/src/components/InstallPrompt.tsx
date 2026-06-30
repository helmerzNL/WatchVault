import { useEffect, useState } from "react";
import { useT } from "../lib/i18n";
import { IconLogo } from "./icons";

interface BIPEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

const DISMISS_KEY = "wv-install-dismissed";

// Surfaces a friendly "install as an app" banner. On Chromium browsers it waits
// for `beforeinstallprompt` and triggers the native install flow; on iOS Safari
// (which has no such event) it shows Add-to-Home-Screen guidance instead.
export function InstallPrompt() {
  const { t } = useT();
  const [deferred, setDeferred] = useState<BIPEvent | null>(null);
  const [ios, setIos] = useState(false);
  const [show, setShow] = useState(false);

  useEffect(() => {
    if (localStorage.getItem(DISMISS_KEY)) return;

    const standalone =
      window.matchMedia("(display-mode: standalone)").matches ||
      (navigator as any).standalone === true;
    if (standalone) return; // already installed

    const ua = navigator.userAgent;
    const isIos = /iphone|ipad|ipod/i.test(ua) && !(window as any).MSStream;
    const isIosSafari = isIos && /safari/i.test(ua) && !/crios|fxios|edgios/i.test(ua);
    if (isIosSafari) {
      setIos(true);
      setShow(true);
      return;
    }

    const onPrompt = (e: Event) => {
      e.preventDefault();
      setDeferred(e as BIPEvent);
      setShow(true);
    };
    window.addEventListener("beforeinstallprompt", onPrompt);
    const onInstalled = () => setShow(false);
    window.addEventListener("appinstalled", onInstalled);
    return () => {
      window.removeEventListener("beforeinstallprompt", onPrompt);
      window.removeEventListener("appinstalled", onInstalled);
    };
  }, []);

  const dismiss = () => {
    setShow(false);
    localStorage.setItem(DISMISS_KEY, "1");
  };

  const install = async () => {
    if (!deferred) return;
    await deferred.prompt();
    await deferred.userChoice.catch(() => {});
    dismiss();
  };

  if (!show) return null;

  return (
    <div className="install-banner glass" role="dialog" aria-label={t("install.title")}>
      <IconLogo size={34} />
      <div className="col" style={{ gap: 2, flex: 1, minWidth: 0 }}>
        <strong>{t("install.title")}</strong>
        <span className="caption">{ios ? t("install.ios") : t("install.body")}</span>
      </div>
      {!ios && (
        <button className="btn btn-primary btn-sm" onClick={install}>
          {t("install.action")}
        </button>
      )}
      <button className="btn btn-ghost btn-sm install-x" onClick={dismiss} aria-label={t("install.dismiss")}>
        ✕
      </button>
    </div>
  );
}
