// Serve the built PWA (app/frontend/dist) from the same origin as /api.
// Same origin is what the manifest, the service worker and the web share
// target require. Node built-ins only.
import fs from 'node:fs';
import path from 'node:path';

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.webmanifest': 'application/manifest+json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.webp': 'image/webp',
  '.gif': 'image/gif',
  '.ico': 'image/x-icon',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
  '.ttf': 'font/ttf',
  '.txt': 'text/plain; charset=utf-8',
  '.map': 'application/json; charset=utf-8',
  '.wasm': 'application/wasm',
  '.webm': 'video/webm',
  '.mp4': 'video/mp4',
  '.mp3': 'audio/mpeg',
};

const NO_CACHE = new Set(['index.html', 'sw.js', 'manifest.webmanifest', 'registerSW.js']);

function cacheControl(rel) {
  const base = path.posix.basename(rel);
  if (NO_CACHE.has(base)) return 'no-cache';
  if (rel.startsWith('assets/')) return 'public, max-age=31536000, immutable';
  return 'no-cache';
}

async function stat(file) {
  try { return await fs.promises.stat(file); } catch { return null; }
}

/**
 * Returns `async (req, res, pathname) => boolean` -- true when a response was
 * written. Order: exact file -> directory index -> SPA fallback (GET/HEAD,
 * extension-less paths) -> false.
 */
export function createStaticHandler({ dir, indexFile = 'index.html' } = {}) {
  const root = path.resolve(dir);

  async function send(res, method, file, rel) {
    const st = await stat(file);
    if (!st || !st.isFile()) return false;
    const ext = path.extname(file).toLowerCase();
    const headers = {
      'Content-Type': MIME[ext] || 'application/octet-stream',
      'Content-Length': st.size,
      'Cache-Control': cacheControl(rel),
      'Last-Modified': st.mtime.toUTCString(),
    };
    if (path.posix.basename(rel) === 'sw.js') headers['Service-Worker-Allowed'] = '/';
    res.writeHead(200, headers);
    if (method === 'HEAD') { res.end(); return true; }
    await new Promise((resolve) => {
      const stream = fs.createReadStream(file);
      stream.on('error', () => { res.destroy(); resolve(); });
      stream.on('end', resolve);
      res.on('close', resolve);
      stream.pipe(res);
    });
    return true;
  }

  return async function serveStatic(req, res, pathname) {
    if (req.method !== 'GET' && req.method !== 'HEAD') return false;
    let decoded;
    try { decoded = decodeURIComponent(pathname); } catch { return false; }
    const rel = path.posix.normalize(decoded).replace(/^\/+/, '');
    const file = path.resolve(root, rel || '.');
    if (file !== root && !file.startsWith(root + path.sep)) return false; // traversal
    const st = await stat(file);
    if (st?.isFile()) return send(res, req.method, file, rel);
    if (st?.isDirectory()) {
      const idx = path.join(file, indexFile);
      if (await send(res, req.method, idx, path.posix.join(rel, indexFile))) return true;
    }
    if (!path.extname(rel)) {
      // SPA fallback: /share?text=... or /journey/abc must load the app shell
      return send(res, req.method, path.join(root, indexFile), indexFile);
    }
    return false;
  };
}
