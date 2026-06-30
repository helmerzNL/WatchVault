// Accent-aware app branding: the WatchVault mark, browser favicon, iOS touch
// icon and the theme-color meta all follow the user's chosen accent colour.

/** Darken a #rrggbb colour by `amount` (0..1) toward black. */
export function darkenHex(hex: string, amount = 0.28): string {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex.trim());
  if (!m) return hex;
  const n = parseInt(m[1], 16);
  const f = (c: number) => Math.max(0, Math.min(255, Math.round(c * (1 - amount))));
  const r = f((n >> 16) & 255), g = f((n >> 8) & 255), b = f(n & 255);
  return `#${((1 << 24) | (r << 16) | (g << 8) | b).toString(16).slice(1)}`;
}

/** The WatchVault logo as an SVG string, tinted with the accent (gradient
 *  accent → darkened accent). Mirrors the in-app inline logo. */
export function logoSvg(accent: string): string {
  const dark = darkenHex(accent, 0.3);
  return (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64">' +
    '<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">' +
    `<stop offset="0" stop-color="${accent}"/><stop offset="1" stop-color="${dark}"/>` +
    '</linearGradient></defs>' +
    '<rect width="64" height="64" rx="14" fill="url(#g)"/>' +
    '<path d="M20 22h24a3 3 0 0 1 3 3v14a3 3 0 0 1-3 3H20a3 3 0 0 1-3-3V25a3 3 0 0 1 3-3z" fill="rgba(255,255,255,0.18)"/>' +
    '<path d="M28 28l10 6-10 6z" fill="#fff"/>' +
    '</svg>'
  );
}

export function logoDataUri(accent: string): string {
  return `data:image/svg+xml,${encodeURIComponent(logoSvg(accent))}`;
}

/** Recolour the browser/PWA icon and theme colour to match the accent. The
 *  favicon and apple-touch-icon update live; an already-installed PWA keeps the
 *  OS-cached home-screen icon until it is reinstalled. */
export function applyBrandIcons(accent: string): void {
  if (!accent) return;
  const href = logoDataUri(accent);
  const ensure = (rel: string): HTMLLinkElement => {
    let el = document.head.querySelector<HTMLLinkElement>(`link[rel="${rel}"]`);
    if (!el) {
      el = document.createElement("link");
      el.rel = rel;
      document.head.appendChild(el);
    }
    return el;
  };
  const icon = ensure("icon");
  icon.type = "image/svg+xml";
  icon.href = href;
  ensure("apple-touch-icon").href = href;

  const meta = document.head.querySelector<HTMLMetaElement>('meta[name="theme-color"]');
  if (meta) meta.content = accent;
}
