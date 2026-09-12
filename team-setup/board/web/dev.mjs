import { spawn } from "node:child_process"
import { createHash } from "node:crypto"
import { realpathSync } from "node:fs"
import { fileURLToPath } from "node:url"
import path from "node:path"

const here = path.dirname(fileURLToPath(import.meta.url))
const root = realpathSync(path.resolve(here, "../../.."))
const port = process.env.HACKOS_API_PORT || "8420"
const expected = createHash("sha256").update(root).digest("hex").slice(0, 16)
const children = []
let stopping = false
const stop = (code = 0) => {
  if (stopping) return
  stopping = true
  for (const child of children) child.kill("SIGTERM")
  process.exitCode = code
}
process.on("SIGINT", () => stop())
process.on("SIGTERM", () => stop())

async function health() {
  try {
    const response = await fetch(`http://127.0.0.1:${port}/api/state`, {
      signal: AbortSignal.timeout(2500),
    })
    if (!response.ok)
      throw new Error("The API is reachable but cannot read its state")
    const data = await response.json()
    if (data.workspace_id !== expected)
      throw new Error(
        `Port ${port} belongs to another server or an older API. Stop it yourself or set HACKOS_API_PORT.`,
      )
    return true
  } catch (error) {
    if (error.cause?.code === "ECONNREFUSED") return false
    throw error
  }
}

try {
  if (!(await health())) {
    const api = spawn(
      process.env.PYTHON || "python3",
      [path.join(here, "../serve.py"), port],
      { cwd: root, stdio: "inherit" },
    )
    children.push(api)
    api.on("error", (error) => {
      console.error(error.message)
      stop(1)
    })
    let ready = false
    for (let n = 0; n < 30 && !stopping; n++) {
      await new Promise((resolve) => setTimeout(resolve, 150))
      if (await health()) {
        ready = true
        break
      }
      if (api.exitCode !== null) break
    }
    if (!ready)
      throw new Error(
        "The Python API did not become ready. Check its startup output.",
      )
    api.on("exit", (code) => {
      if (!stopping) stop(code || 1)
    })
  }
  const vite = spawn(
    process.execPath,
    [path.join(here, "node_modules/vite/bin/vite.js"), "--host", "127.0.0.1"],
    { cwd: here, stdio: "inherit" },
  )
  children.push(vite)
  vite.on("error", (error) => {
    console.error(error.message)
    stop(1)
  })
  vite.on("exit", (code) => stop(code || 0))
} catch (error) {
  console.error(error.message)
  stop(1)
}
