// Seed route + static serving + the server's request ordering, over a real
// listening socket on an ephemeral port. Uses a tiny dist fixture.
import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { createSeedService, registerRoutes } from './routes/pwa-shell.js';
import { Router, createApp } from '../../server.js';

let dir, server, base;

before(async () => {
  dir = mkdtempSync(path.join(tmpdir(), 'dist-'));
  mkdirSync(path.join(dir, 'assets'));
  writeFileSync(path.join(dir, 'index.html'), '<!doctype html><div id="root"></div>');
  writeFileSync(path.join(dir, 'manifest.webmanifest'), '{"name":"error404"}');
  writeFileSync(path.join(dir, 'sw.js'), '// sw');
  writeFileSync(path.join(dir, 'assets', 'app-abc123.js'), 'console.log(1)');
  server = createApp({ env: { STATIC_DIR: dir, CORS_ORIGIN: 'http://localhost:5173' } });
  await new Promise((r) => server.listen(0, '127.0.0.1', r));
  base = `http://127.0.0.1:${server.address().port}`;
});

after(async () => {
  await new Promise((r) => server.close(r));
  rmSync(dir, { recursive: true, force: true });
});

test('seed journey has two legs with EVA numbers, transfer and coordinates', () => {
  const router = new Router();
  registerRoutes(router, { env: {} });
  const seed = router.match('GET', '/api/seed/demo').handler({});
  assert.equal(seed.source, 'seed');
  assert.equal(seed.legs.length, 2);
  assert.deepEqual(seed.legs.map((l) => l.trainId), ['RB 16', 'S 8']);
  assert.equal(seed.legs[0].from.evaNumber, '8000284');
  assert.equal(seed.legs[0].transferMinutes, 16);
  assert.ok(seed.legs.every((l) => typeof l.from.lat === 'number' && typeof l.to.lon === 'number'));
  const again = createSeedService().demo();
  again.legs.pop();
  assert.equal(createSeedService().demo().legs.length, 2, 'fixture is cloned per call');
});

test('health carries ok:true and CORS preflight answers 204', async () => {
  const h = await (await fetch(`${base}/api/health`)).json();
  assert.equal(h.ok, true);
  assert.equal(h.status, 'ok');
  const pre = await fetch(`${base}/api/predict`, { method: 'OPTIONS', headers: { Origin: 'http://localhost:5173' } });
  assert.equal(pre.status, 204);
  assert.equal(pre.headers.get('access-control-allow-origin'), 'http://localhost:5173');
});

test('static files, MIME types, cache headers, SPA fallback and API 404 ordering', async () => {
  const idx = await fetch(`${base}/`);
  assert.equal(idx.status, 200);
  assert.match(idx.headers.get('content-type'), /text\/html/);
  assert.equal(idx.headers.get('cache-control'), 'no-cache');
  const man = await fetch(`${base}/manifest.webmanifest`);
  assert.match(man.headers.get('content-type'), /application\/manifest\+json/);
  const sw = await fetch(`${base}/sw.js`);
  assert.equal(sw.headers.get('cache-control'), 'no-cache');
  assert.equal(sw.headers.get('service-worker-allowed'), '/');
  const asset = await fetch(`${base}/assets/app-abc123.js`);
  assert.match(asset.headers.get('content-type'), /text\/javascript/);
  assert.match(asset.headers.get('cache-control'), /immutable/);
  const spa = await fetch(`${base}/share?text=hello`);
  assert.equal(spa.status, 200);
  assert.match(await spa.text(), /id="root"/);
  const head = await fetch(`${base}/share`, { method: 'HEAD' });
  assert.equal(head.status, 200);
  const api404 = await fetch(`${base}/api/nope`);
  assert.equal(api404.status, 404);
  assert.match((await api404.json()).error, /No route/);
  const missingAsset = await fetch(`${base}/assets/nope.js`);
  assert.equal(missingAsset.status, 404);
  const traversal = await fetch(`${base}/..%2F..%2Fpackage.json`);
  assert.notEqual(traversal.status, 200);
});

test('product endpoints answer over HTTP end to end', async () => {
  const seed = await (await fetch(`${base}/api/seed/demo`)).json();
  const pRes = await fetch(`${base}/api/predict`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(seed) });
  assert.equal(pRes.status, 200);
  const prediction = await pRes.json();
  assert.equal(prediction.legs.length, 2);
  const rRes = await fetch(`${base}/api/recommend`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ journey: seed, prediction, doorToStationMin: 15 }) });
  const rec = await rRes.json();
  assert.ok(['good', 'add-buffer', 'take-alternative'].includes(rec.verdict));
  const rrRes = await fetch(`${base}/api/reroute`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ journey: seed, missedLegIndex: 0 }) });
  assert.equal((await rrRes.json()).options.length, 3);
  const causes = await (await fetch(`${base}/api/causes?eva=8000261`)).json();
  assert.equal(causes.station.name, 'München Hbf');
  const parse = await fetch(`${base}/api/journeys/parse`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ text: 'RB16 (59143)\nFrom 04:34 Nürnberg Hbf, Platform 5\nTo 07:25 München Hbf, Platform 21' }) });
  assert.equal((await parse.json()).legs[0].trainId, 'RB 16');
  const junk = await fetch(`${base}/api/journeys/parse`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ text: 'hello' }) });
  assert.equal(junk.status, 400);
});
