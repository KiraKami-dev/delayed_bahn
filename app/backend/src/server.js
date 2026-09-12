// Minimal HTTP server: Node built-ins only. Features register routes on the
// router; no framework so `npm run dev` works with zero installs.
import http from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { registerRoutes as registerTrainingJobs } from './features/training-jobs/routes/training-jobs.js';
import { registerRoutes as registerPwaShell, createStaticHandler } from './features/pwa-shell/routes/pwa-shell.js';
import { registerRoutes as registerShareParser } from './features/share-parser/routes/share-parser.js';
import { registerRoutes as registerDelayPrediction } from './features/delay-prediction/routes/delay-prediction.js';
import { registerRoutes as registerRecommendation } from './features/recommendation/routes/recommendation.js';
import { registerRoutes as registerCauses } from './features/causes/routes/causes.js';

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
  // Contract says { ok: true }; the older fields stay for existing callers.
  router.get('/api/health', async () => ({ ok: true, status: 'ok', service: 'app-backend', time: new Date().toISOString() }));
  registerTrainingJobs(router, { env });
  registerPwaShell(router, { env });
  registerShareParser(router, { env });
  const predict = registerDelayPrediction(router, { env });
  registerRecommendation(router, { env, predict });
  registerCauses(router, { env });
  const serveStatic = createStaticHandler({ dir: env.STATIC_DIR || path.join(__dirname, '..', '..', 'frontend', 'dist') });

  return http.createServer(async (req, res) => {
    const url = new URL(req.url, 'http://localhost');
    if (env.CORS_ORIGIN) {
      // Dev only: the Vite dev server on another port calling :8000 directly.
      res.setHeader('Access-Control-Allow-Origin', env.CORS_ORIGIN);
      res.setHeader('Access-Control-Allow-Methods', 'GET,POST,DELETE,OPTIONS');
      res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
      res.setHeader('Access-Control-Max-Age', '600');
      res.setHeader('Vary', 'Origin');
    }
    if (req.method === 'OPTIONS') { res.writeHead(204); return res.end(); }
    const matched = router.match(req.method, url.pathname);
    if (!matched) {
      if (url.pathname.startsWith('/api/')) return sendJson(res, 404, { error: `No route for ${req.method} ${url.pathname}` });
      if (await serveStatic(req, res, url.pathname)) return;
      return sendJson(res, 404, { error: `No route for ${req.method} ${url.pathname}`, hint: 'Build the PWA first: npm --prefix app/frontend run build (or set STATIC_DIR)' });
    }
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
    console.log(`  GET  /api/seed/demo | /api/causes?eva=   POST /api/journeys/parse | /api/predict | /api/recommend | /api/reroute`);
    console.log(`  static PWA from ${process.env.STATIC_DIR || path.join(__dirname, '..', '..', 'frontend', 'dist')}`);
  });
}
