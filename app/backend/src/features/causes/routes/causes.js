// causes: GET /api/causes?eva=8000261  (or ?station=München Hbf)
// Cause-family shares per station, from the IRIS cause codes the db_route
// pipeline folds into families (works, weather, technical, knock_on, staff,
// external) plus the unattributed floor.
// With CAUSES_URL set the lookup is forwarded to the Python route server
// (app/agents/src/features/db_route/serve_route.py), which answers from the
// registry's per-station cause-share series. Without it, or when that server
// is down or has no record for the station, the bundled fixture answers and
// says so (`illustrative: true`, `fallbackFrom`).
import { readFileSync } from 'node:fs';
import { createStationResolver } from '../../share-parser/stations.js';

const SOURCE = 'piebro/deutsche-bahn-data (DB IRIS), Munich region, illustrative until the db_route pipeline output lands';
const fail = (status, message) => Object.assign(new Error(message), { status });

export function createCausesService({ env = process.env, fixture, stations, fetchImpl = fetch } = {}) {
  const data = fixture ?? JSON.parse(readFileSync(new URL('../fixtures/causes.json', import.meta.url), 'utf8'));
  const resolver = createStationResolver({ env: {}, stations }); // local table only, never the network here
  const remote = env.CAUSES_URL || '';
  const timeoutMs = Number(env.CAUSES_TIMEOUT_MS || 4000);

  function resolve({ eva, station } = {}) {
    let key = eva ? String(eva) : '';
    let name = station || '';
    if (!key && name) key = resolver.resolveLocal(name)?.evaNumber || '';
    if (!key && !name) throw fail(400, 'Pass ?eva=<number> or ?station=<name>');
    if (!name && key) name = resolver.byEva(key)?.name || '';
    return { key, name };
  }

  function fromFixture({ key, name }, fallbackFrom) {
    const entry = data[key] || data.default;
    const st = entry.station || resolver.byEva(key) || { evaNumber: key, name: name || 'unknown station' };
    const families = { ...entry.families };
    const sum = Object.values(families).reduce((a, b) => a + b, 0);
    for (const k of Object.keys(families)) families[k] = Math.round((families[k] / sum) * 1000) / 1000;
    return {
      station: { evaNumber: st.evaNumber, name: st.name },
      attributionRate: entry.attributionRate,
      families,
      top: entry.top,
      sparkline7d: entry.sparkline7d,
      source: SOURCE,
      illustrative: true,
      matched: Boolean(data[key]),
      ...(fallbackFrom ? { fallbackFrom } : {}),
    };
  }

  async function fromRemote({ key, name }) {
    const url = new URL(remote);
    if (name) url.searchParams.set('station', name);
    if (key) url.searchParams.set('eva', key);
    const res = await fetchImpl(url, { signal: AbortSignal.timeout(timeoutMs) });
    if (res.status === 404) return null; // no record for this station: the fixture answers
    if (!res.ok) throw new Error(`causes server replied ${res.status}`);
    const body = await res.json();
    if (!body?.families || !body?.station) throw new Error('causes server reply has no families');
    return {
      ...body,
      station: { evaNumber: body.station.evaNumber || key, name: body.station.name || name },
      top: Array.isArray(body.top) ? body.top : [],
      sparkline7d: Array.isArray(body.sparkline7d) ? body.sparkline7d : [],
      illustrative: false,
    };
  }

  return {
    /** Synchronous with the fixture; a promise when CAUSES_URL is set (the router awaits either). */
    lookup(args = {}) {
      const target = resolve(args);
      if (!remote) return fromFixture(target);
      return fromRemote(target)
        .then((live) => live ?? fromFixture(target, 'no recorded station at the causes server'))
        .catch((e) => fromFixture(target, `causes server unavailable (${e.message})`));
    },
  };
}

export function registerRoutes(router, ctx = {}) {
  const svc = ctx.service || createCausesService(ctx);
  router.get('/api/causes', ({ query }) => svc.lookup({ eva: query.get('eva') || undefined, station: query.get('station') || undefined }));
  return svc;
}
