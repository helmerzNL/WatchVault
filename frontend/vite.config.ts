import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";

// WatchVault PWA. Dev proxies /api and /mcp to the backend; production is
// served by nginx from dist/ on the same origin (so no proxy needed there).
export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      filename: "sw.js",
      includeAssets: ["favicon.svg"],
      manifest: {
        name: "WatchVault",
        short_name: "WatchVault",
        description: "Your household's watch history, in one place.",
        theme_color: "#0a84ff",
        background_color: "#000000",
        display: "standalone",
        orientation: "portrait",
        start_url: "/",
        scope: "/",
        icons: [
          { src: "icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
          { src: "icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
          { src: "icon-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
        ],
      },
      workbox: {
        navigateFallback: "/index.html",
        navigateFallbackDenylist: [/^\/api/, /^\/mcp/],
        runtimeCaching: [
          {
            urlPattern: ({ url }) => url.pathname.startsWith("/api/stats") ||
              url.pathname.startsWith("/api/search"),
            handler: "NetworkFirst",
            options: { cacheName: "wv-data", networkTimeoutSeconds: 5 },
          },
          {
            urlPattern: ({ url }) => url.hostname === "image.tmdb.org",
            handler: "CacheFirst",
            options: {
              cacheName: "wv-posters",
              expiration: { maxEntries: 600, maxAgeSeconds: 60 * 60 * 24 * 30 },
            },
          },
        ],
      },
      devOptions: { enabled: false },
    }),
  ],
  server: {
    port: 7212,
    proxy: {
      "/api": { target: "http://127.0.0.1:7200", changeOrigin: true },
      "/mcp": { target: "http://127.0.0.1:7211", changeOrigin: true },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
    chunkSizeWarningLimit: 700,
    rollupOptions: {
      output: {
        manualChunks: {
          react: ["react", "react-dom", "react-router-dom"],
          charts: ["recharts"],
        },
      },
    },
  },
});
