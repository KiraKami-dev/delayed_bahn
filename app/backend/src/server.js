// Minimal HTTP server: Node built-ins only. Features register routes on the
// router; no framework so `npm run dev` works with zero installs.
import http from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { registerRoutes as registerTrainingJobs } from './features/training-jobs/routes/training-jobs.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export function loadDotenv(file = path.join(__dirname, '..', '.env')) {
  try {
    process.loadEnvFile(file);
    return true;
  } catch {
    return false; // no .env yet -- env vars from the shell still apply
  }
}

export class Router {
  constructor() { this.routes = []; }
  add(method, pattern, handler) {
    const keys = [];
    const re = new RegExp('^' + pattern.replace(/:(\w+)/g, (_, k) => { keys.push(k); return '([^/]+)'; }) + '/?$');
    this.routes.push({ method, re, keys, handler });
    return this;
  }
  get(p, h) { return this.add('GET', p, h); }
  post(p, h) { return this.add('POST', p, h); }
  delete(p, h) { return this.add('DELETE', p, h); }
  match(method, pathname) {
    for (const r of this.routes) {
      if (r.method !== method) continue;
      const m = r.re.exec(pathname);
      if (!m) continue;
      const params = Object.fromEntries(r.keys.map((k, i) => [k, decodeURIComponent(m[i + 1])]));
      return { handler: r.handler, params };
    }
    return null;
  }
}

export class HttpError extends Error {
  constructor(status, message, details) { super(message); this.status = status; this.details = details; }
}

async function readJson(req) {
  const chunks = [];
  for await (const c of req) chunks.push(c);
  if (chunks.length === 0) return {};
  const text = Buffer.concat(chunks).toString('utf8');
  if (!text.trim()) return {};
  try { return JSON.parse(text); } catch { throw new HttpError(400, 'Body must be valid JSON'); }
}

export function sendJson(res, status, payload) {
  const body = JSON.stringify(payload, null, 2);
  res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8', 'Content-Length': Buffer.byteLength(body) });
  res.end(body);
}

export function createApp({ env = process.env } = {}) {
  const router = new Router();
  router.get('/api/health', async () => ({ status: 'ok', service: 'app-backend', time: new Date().toISOString() }));
  registerTrainingJobs(router, { env });

  return http.createServer(async (req, res) => {
    const url = new URL(req.url, 'http://localhost');
    const matched = router.match(req.method, url.pathname);
    if (!matched) return sendJson(res, 404, { error: `No route for ${req.method} ${url.pathname}` });
    try {
      const body = req.method === 'GET' || req.method === 'DELETE' ? {} : await readJson(req);
      const result = await matched.handler({ params: matched.params, query: url.searchParams, body, req, res });
      if (res.writableEnded) return; // handler streamed its own response
      sendJson(res, 200, result ?? {});
    } catch (err) {
      const status = err.status ?? 500;
      if (status >= 500) console.error(err);
      sendJson(res, status, { error: err.message, details: err.details ?? err.body ?? undefined });
    }
  });
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  loadDotenv();
  const port = Number(process.env.PORT || 8000);
  createApp().listen(port, () => {
    console.log(`app-backend listening on http://localhost:${port}`);
    console.log(`  GET  /api/health`);
    console.log(`  GET  /api/training/catalog | /whoami | /jobs | /jobs/:id | /jobs/:id/logs`);
    console.log(`  POST /api/training/jobs | /jobs/dry-run | /jobs/:id/cancel   DELETE /jobs/:id`);
  });
}
