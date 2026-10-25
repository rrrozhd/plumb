import { spawn, type ChildProcess } from "node:child_process"
import path from "node:path"
import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig, type Plugin } from "vite"

// `npm run dev` also starts the control server (server.mjs, 127.0.0.1:8410) unless one already answers.
function controlServer(): Plugin {
  let child: ChildProcess | undefined
  return {
    name: "plumb-control-server",
    async configureServer() {
      const up = await fetch("http://127.0.0.1:8410/api/health").then(() => true, () => false)
      if (!up) child = spawn("node", ["server.mjs"], { cwd: __dirname, stdio: "inherit" })
    },
    buildEnd() { child?.kill() },
  }
}

export default defineConfig({
  plugins: [react(), tailwindcss(), controlServer()],
  resolve: { alias: { "@": path.resolve(__dirname, "./src") } },
  server: { host: "127.0.0.1", port: 5173, proxy: { "/api": "http://127.0.0.1:8410" } },
})
