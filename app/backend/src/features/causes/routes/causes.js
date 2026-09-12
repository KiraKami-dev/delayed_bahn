// causes: GET /api/causes?eva=8000261  (or ?station=München Hbf)
// Cause-family shares per station, from the IRIS cause codes the db_route
// pipeline folds into families (works, weather, technical, knock_on, staff,
// external) plus the unattributed floor. Fixture-backed until the pipeline
// output lands; the `source` field says so.
import { readFileSync } from 'node:fs';
import { createStationResolver } from '../../share-parser/stations.js';

const SOURCE = 'piebro/deutsche-bahn-data (DB IRIS), Munich region, illustrative until the db_route pipeline output lands';
const fail = (status, message) => Object.assign(new Error(message), { status });

export function createCausesService({ env = process.env, fixture, stations } = {}) {
  const data = fixture ?? JSON.parse(readFileSync(new URL('../fixtures/causes.json', import.meta.url), 'utf8'));
  const resolver = createStationResolver({ env: {}, stations }); // local table only, never the network here

  return {
    lookup({ eva, station } = {}) {
      let key = eva ? String(eva) : '';
      let name = station || '';
      if (!key && name) key = resolver.resolveLocal(name)?.evaNumber || '';
      if (!key && !name) throw fail(400, 'Pass ?eva=<number> or ?station=<name>');
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
      };
    },
  };
}

export function registerRoutes(router, ctx = {}) {
  const svc = ctx.service || createCausesService(ctx);
  router.get('/api/causes', ({ query }) => svc.lookup({ eva: query.get('eva') || undefined, station: query.get('station') || undefined }));
  return svc;
}
