import { fileURLToPath, URL } from "node:url"
import { defineConfig, type ProxyOptions } from "vite"
import react from "@vitejs/plugin-react"
import tailwindcss from "@tailwindcss/vite"

const target = `http://127.0.0.1:${process.env.HACKOS_API_PORT || "8420"}`
const apiProxy: ProxyOptions = {
  target,
  changeOrigin: true,
  configure(proxy) {
    proxy.on("proxyReq", (outgoing, request, response) => {
      const origin = request.headers.origin
      if (origin && origin !== `http://${request.headers.host}`) {
        outgoing.destroy()
        if ("writeHead" in response) {
          response.writeHead(403)
          response.end("Cross-origin requests are not permitted")
        }
        return
      }
      if (origin) outgoing.setHeader("Origin", target)
    })
  },
}

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    cors: false,
    proxy: { "/api": apiProxy },
  },
  preview: { host: "127.0.0.1", cors: false, proxy: { "/api": apiProxy } },
  build: { sourcemap: false },
})
