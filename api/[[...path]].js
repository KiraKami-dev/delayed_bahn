// Vercel serverless entry: every /api/* request is handed to the same Node
// server the backend runs locally (app/backend/src/server.js). Static files
// come from app/frontend/dist, served by Vercel itself (see vercel.json).
import { createApp } from "../app/backend/src/server.js"

const server = createApp({ env: { ...process.env, STATIC_DIR: "/nonexistent" } })

export default function handler(req, res) {
  server.emit("request", req, res)
}
