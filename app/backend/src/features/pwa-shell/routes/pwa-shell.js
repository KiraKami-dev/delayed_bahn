// pwa-shell: GET /api/seed/demo (the storyline journey, offline fallback for
// every screen) and the static handler that serves the built PWA.
import { readFileSync } from 'node:fs';

export { createStaticHandler } from '../static.js';

export function createSeedService({ fixture } = {}) {
  const seed = fixture ?? JSON.parse(readFileSync(new URL('../fixtures/seed-journey.json', import.meta.url), 'utf8'));
  return { demo: () => structuredClone(seed) };
}

export function registerRoutes(router, ctx = {}) {
  const svc = ctx.service || createSeedService(ctx);
  router.get('/api/seed/demo', () => svc.demo());
  return svc;
}
