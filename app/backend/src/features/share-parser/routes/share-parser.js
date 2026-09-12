// share-parser: POST /api/journeys/parse  { text } -> Journey (contract).
// The text is what the DB Navigator app hands to the share sheet.
import { tokenize, parseConnections, pickFirstComplete, materialise, journeyId } from '../grammar.js';
import { createStationResolver } from '../stations.js';
import { createVbidResolver } from '../vbid.js';

const fail = (status, message, details) => Object.assign(new Error(message), { status, details });

export function createShareParserService({ env = process.env, stations, fetchImpl = fetch, now = () => new Date() } = {}) {
  const resolver = createStationResolver({ env, stations, fetchImpl });
  const vbid = createVbidResolver({ env, fetchImpl });

  async function withStations(legs) {
    return Promise.all(legs.map(async (l) => {
      const from = typeof l.from === 'string' ? await resolver.resolve(l.from) : { ...(await resolver.resolve(l.from.name)), ...stripEmpty(l.from) };
      const to = typeof l.to === 'string' ? await resolver.resolve(l.to) : { ...(await resolver.resolve(l.to.name)), ...stripEmpty(l.to) };
      const leg = { trainId: l.trainId, from, to, plannedDeparture: l.plannedDeparture, plannedArrival: l.plannedArrival };
      if (typeof l.transferMinutes === 'number') leg.transferMinutes = l.transferMinutes;
      if (l.trainNumber) leg.trainNumber = l.trainNumber;
      if (l.fromPlatform) leg.fromPlatform = l.fromPlatform;
      if (l.toPlatform) leg.toPlatform = l.toPlatform;
      return leg;
    }));
  }

  return {
    resolver,
    async parse(text) {
      const tokens = tokenize(text);
      const conns = parseConnections(tokens);
      const chosen = pickFirstComplete(conns);
      if (chosen) {
        const legs = await withStations(materialise(chosen, { now: now() }));
        for (let i = 0; i < legs.length - 1; i++) delete legs[legs.length - 1].transferMinutes;
        return { id: journeyId(legs), legs, source: 'db-share', ...(chosen.url ? { url: chosen.url } : {}) };
      }
      const linkOnly = conns.find((c) => c.vbid);
      if (linkOnly) {
        if (vbid.enabled) {
          try {
            const legs = await withStations(await vbid.resolve(linkOnly.vbid));
            return { id: journeyId(legs), legs, source: 'db-share', url: linkOnly.url };
          } catch (e) {
            throw fail(422, `Could not resolve the bahn.de link (${e.message}); paste the connection details instead`, { vbid: linkOnly.vbid, resolverEnabled: true });
          }
        }
        throw fail(422, 'Share text only contains a bahn.de link; paste the connection details (trains, times, stations) instead', { vbid: linkOnly.vbid, resolverEnabled: false });
      }
      throw fail(400, 'No complete connection found in text', {
        connectionsSeen: conns.length,
        legsSeen: conns.reduce((n, c) => n + c.legs.length, 0),
        hint: 'Expected lines like "RB16 (59143)", "From 04:34 Nürnberg Hbf, Platform 5", "To 07:25 München Hbf, Platform 21"',
      });
    },
  };
}

function stripEmpty(o) {
  return Object.fromEntries(Object.entries(o).filter(([, v]) => v !== '' && v !== undefined && v !== null));
}

export function registerRoutes(router, ctx = {}) {
  const svc = ctx.service || createShareParserService(ctx);
  router.post('/api/journeys/parse', async ({ body }) => {
    if (typeof body?.text !== 'string' || !body.text.trim()) throw fail(400, 'Body must be { text: string }');
    return svc.parse(body.text);
  });
  return svc;
}
