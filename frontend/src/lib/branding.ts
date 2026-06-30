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

function roundRectPath(ctx: CanvasRenderingContext2D, x: number, y: number,
                       w: number, h: number, r: number): void {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

/** Rasterise the accent-tinted WatchVault mark to a PNG data URL. Used for the
 *  iOS touch icon and the dynamic web-app-manifest icons, which (unlike the
 *  favicon) are not reliably rendered from SVG. `maskable` fills the whole
 *  square (full-bleed, safe-zone glyph) for Android adaptive icons. */
export function rasterIcon(accent: string, size: number, maskable = false): string {
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = size;
  const ctx = canvas.getContext("2d");
  if (!ctx) return logoDataUri(accent);
  const grad = ctx.createLinearGradient(0, 0, size, size);
  grad.addColorStop(0, accent);
  grad.addColorStop(1, darkenHex(accent, 0.3));
  ctx.fillStyle = grad;
  if (maskable) {
    ctx.fillRect(0, 0, size, size);
  } else {
    roundRectPath(ctx, 0, 0, size, size, size * 0.22);
    ctx.fill();
  }
  // Glyph is authored in the 64×64 logo space, then scaled (and shrunk into the
  // central safe zone for maskable icons so Android cropping never clips it).
  ctx.save();
  ctx.translate(size / 2, size / 2);
  const k = (size / 64) * (maskable ? 0.7 : 0.92);
  ctx.scale(k, k);
  ctx.translate(-32, -32);
  roundRectPath(ctx, 20, 22, 24, 20, 3);
  ctx.fillStyle = "rgba(255,255,255,0.20)";
  ctx.fill();
  ctx.beginPath();
  ctx.moveTo(28, 28);
  ctx.lineTo(38, 34);
  ctx.lineTo(28, 40);
  ctx.closePath();
  ctx.fillStyle = "#fff";
  ctx.fill();
  ctx.restore();
  return canvas.toDataURL("image/png");
}

/** Recolour the browser/PWA icon and theme colour to match the accent. The
 *  favicon and apple-touch-icon update live; an already-installed PWA keeps the
 *  OS-cached home-screen icon until it is reinstalled. */
export function applyBrandIcons(accent: string): void {
  if (!accent) return;
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
  icon.href = logoDataUri(accent);
  // iOS renders SVG touch icons poorly, so use a rasterised PNG there.
  ensure("apple-touch-icon").href = rasterIcon(accent, 180, false);

  const meta = document.head.querySelector<HTMLMetaElement>('meta[name="theme-color"]');
  if (meta) meta.content = accent;
}

let baseManifest: Promise<Record<string, unknown>> | null = null;
let manifestBlobUrl: string | null = null;
let manifestBusy = false;

function manifestLink(): HTMLLinkElement | null {
  return document.head.querySelector<HTMLLinkElement>('link[rel="manifest"]');
}

/** Load (once) the build-time manifest so we can clone its fields and only
 *  override the accent-dependent ones. The original href is stashed so repeated
 *  recolours never re-fetch the blob we install. */
function loadBaseManifest(link: HTMLLinkElement): Promise<Record<string, unknown>> {
  if (!baseManifest) {
    let href = link.getAttribute("data-base-href");
    if (!href) {
      href = link.getAttribute("href") || "/manifest.webmanifest";
      link.setAttribute("data-base-href", href);
    }
    baseManifest = fetch(href, { credentials: "same-origin" })
      .then((r) => r.json())
      .catch(() => ({
        name: "WatchVault",
        short_name: "WatchVault",
        description: "Your household's watch history, in one place.",
        background_color: "#000000",
        display: "standalone",
        orientation: "portrait",
        start_url: "/",
        scope: "/",
      }));
  }
  return baseManifest;
}

/** Rebuild the web-app manifest with accent-tinted icons and theme colour, and
 *  point the manifest link at the freshly generated blob. This makes the icon
 *  shown when (re)installing the PWA follow the accent. An icon already cached
 *  by the OS for an installed app only refreshes on reinstall. */
export function applyBrandManifest(accent: string): void {
  if (!accent || manifestBusy) return;
  const link = manifestLink();
  if (!link || typeof URL.createObjectURL !== "function") return;
  manifestBusy = true;
  loadBaseManifest(link)
    .then((base) => {
      const manifest = {
        ...base,
        theme_color: accent,
        icons: [
          { src: rasterIcon(accent, 192, false), sizes: "192x192", type: "image/png", purpose: "any" },
          { src: rasterIcon(accent, 512, false), sizes: "512x512", type: "image/png", purpose: "any" },
          { src: rasterIcon(accent, 512, true), sizes: "512x512", type: "image/png", purpose: "maskable" },
        ],
      };
      const blob = new Blob([JSON.stringify(manifest)], { type: "application/manifest+json" });
      const url = URL.createObjectURL(blob);
      if (manifestBlobUrl) URL.revokeObjectURL(manifestBlobUrl);
      manifestBlobUrl = url;
      link.setAttribute("href", url);
    })
    .catch(() => {})
    .finally(() => { manifestBusy = false; });
}
