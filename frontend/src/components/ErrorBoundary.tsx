import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props { children: ReactNode; }
interface State { error: Error | null; info: ErrorInfo | null; }

const RECOVERY_KEY = "wv-asset-recovery";

function isChunkError(msg: string): boolean {
  return /(dynamically imported module|importing a module script failed|ChunkLoadError|Loading chunk)/i.test(msg);
}

// Top-level safety net. A blank (black) page means an uncaught error crashed the
// React root before anything rendered into #root. This boundary turns that into a
// recoverable screen, surfaces the actual error so it can be diagnosed, and
// auto-recovers once from stale-asset errors that follow a PWA update (a cached
// index.html referencing a purged hashed chunk).
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null, info: null };

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    this.setState({ info });
    // Surface the real error for diagnosis (self-hosted, no remote logging).
    console.error("[WatchVault] render error:", error, info?.componentStack);
    if (isChunkError(error?.message || "")) {
      try {
        if (!sessionStorage.getItem(RECOVERY_KEY)) {
          sessionStorage.setItem(RECOVERY_KEY, String(Date.now()));
          void this.hardReload();
        }
      } catch {
        /* sessionStorage unavailable — fall through to the manual reload button */
      }
    }
  }

  hardReload = async () => {
    try {
      if (typeof caches !== "undefined" && caches.keys) {
        const keys = await caches.keys();
        await Promise.all(keys.map((k) => caches.delete(k)));
      }
      if (navigator.serviceWorker?.getRegistrations) {
        const regs = await navigator.serviceWorker.getRegistrations();
        await Promise.all(regs.map((r) => r.unregister()));
      }
    } catch {
      /* best effort — reload regardless */
    }
    location.reload();
  };

  render() {
    const { error, info } = this.state;
    if (error) {
      return (
        <div className="center-screen">
          <div className="card" style={{ maxWidth: 560, textAlign: "center", gap: 14 }}>
            <h1 className="title">Something went wrong</h1>
            <p className="muted">The app hit an unexpected error. Reloading usually fixes it.</p>
            <button className="btn btn-primary" onClick={this.hardReload}>Reload</button>
            <details style={{ textAlign: "left", marginTop: 8 }}>
              <summary className="muted" style={{ cursor: "pointer" }}>Error details</summary>
              <pre style={{
                whiteSpace: "pre-wrap", wordBreak: "break-word", fontSize: "0.75rem",
                marginTop: 8, maxHeight: 280, overflow: "auto", opacity: 0.85,
              }}>
                {String(error?.stack || error?.message || error)}
                {info?.componentStack ? `\n\nComponent stack:${info.componentStack}` : ""}
              </pre>
            </details>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
