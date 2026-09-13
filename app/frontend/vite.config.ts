import { fileURLToPath, URL } from "node:url"
import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"
import tailwindcss from "@tailwindcss/vite"
import { VitePWA } from "vite-plugin-pwa"

const apiTarget = `http://127.0.0.1:${process.env.API_PORT || "8000"}`

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      registerType: "autoUpdate",
      includeAssets: ["favicon.svg", "icons/*.png", "seed/*.json", "proof.json"],
      manifest: {
        id: "/",
        name: "error404 — A clearer way to travel",
        short_name: "error404",
        description:
          "Share a Deutsche Bahn connection and see the probability your plan fails, plus what to do about it.",
        start_url: "/",
        scope: "/",
        display: "standalone",
        orientation: "any",
        background_color: "#f7f8f2",
        theme_color: "#f7f8f2",
        icons: [
          { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
          { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png" },
          {
            src: "/icons/icon-maskable-512.png",
            sizes: "512x512",
            type: "image/png",
            purpose: "maskable",
          },
        ],
        share_target: {
          action: "/share",
          method: "GET",
          params: { title: "title", text: "text", url: "url" },
        },
      } as Record<string, unknown>,
      workbox: {
        globPatterns: ["**/*.{js,css,html,svg,png,jpg,json,woff2}"],
        maximumFileSizeToCacheInBytes: 4 * 1024 * 1024,
        navigateFallback: "/index.html",
        navigateFallbackDenylist: [/^\/api\//],
        runtimeCaching: [
          {
            urlPattern: /^https:\/\/(tiles\.openfreemap\.org|server\.arcgisonline\.com)\/.*/i,
            handler: "CacheFirst",
            options: {
              cacheName: "tiles",
              expiration: { maxEntries: 3000, maxAgeSeconds: 7 * 24 * 3600 },
              cacheableResponse: { statuses: [0, 200] },
            },
          },
          {
            urlPattern: /\/api\/(seed\/demo|causes)/,
            handler: "NetworkFirst",
            options: { cacheName: "api-seed", networkTimeoutSeconds: 3 },
          },
        ],
      },
      devOptions: { enabled: false },
    }),
  ],
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    proxy: { "/api": { target: apiTarget, changeOrigin: true } },
  },
  preview: {
    host: "127.0.0.1",
    proxy: { "/api": { target: apiTarget, changeOrigin: true } },
  },
  build: { sourcemap: false, outDir: "dist" },
})
