// Causes lookup: fixture by default, the Python route server when CAUSES_URL is set,
// and an honest fixture fallback when that server is down or has no record.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createCausesService } from './routes/causes.js';

const live = {
  station: { evaNumber: '', name: 'München Hbf' },
  attributionRate: 0.54,
  families: { works: 0.051, weather: 0.003, technical: 0.172, knock_on: 0.315, staff: 0, external: 0, unattributed: 0.46 },
  top: [{ code: 43, text: 'knock-on', family: 'knock_on', share: 0.315 }],
  sparkline7d: [{ date: '2026-07-25', meanDelayMin: 6.5 }],
  source: 'piebro/deutsche-bahn-data (DB IRIS cause codes), München Hbf',
  illustrative: false,
};
const reply = (status, body) => ({ ok: status < 400, status, json: async () => body });

test('without CAUSES_URL the fixture answers and is marked illustrative', async () => {
  const svc = createCausesService({ env: {} });
  const out = await svc.lookup({ eva: '8000261' });
  assert.equal(out.illustrative, true);
  assert.equal(out.station.evaNumber, '8000261');
  assert.ok(out.families.unattributed > 0);
});

test('with CAUSES_URL the route server answers, keeping the caller eva', async () => {
  const calls = [];
  const svc = createCausesService({ env: { CAUSES_URL: 'http://model.test/causes' }, fetchImpl: async (url) => { calls.push(String(url)); return reply(200, live); } });
  const out = await svc.lookup({ eva: '8000261', station: 'München Hbf' });
  assert.equal(out.illustrative, false);
  assert.equal(out.station.evaNumber, '8000261');
  assert.equal(out.families.knock_on, 0.315);
  assert.match(calls[0], /station=M%C3%BCnchen\+Hbf|station=M%C3%BCnchen%20Hbf/);
  assert.match(calls[0], /eva=8000261/);
});

test('a 404 from the route server falls back to the fixture and says why', async () => {
  const svc = createCausesService({ env: { CAUSES_URL: 'http://model.test/causes' }, fetchImpl: async () => reply(404, { error: 'no recorded station matches' }) });
  const out = await svc.lookup({ station: 'Nowhere' });
  assert.equal(out.illustrative, true);
  assert.match(out.fallbackFrom, /no recorded station/);
});

test('a dead route server falls back to the fixture and says why', async () => {
  const svc = createCausesService({ env: { CAUSES_URL: 'http://model.test/causes' }, fetchImpl: async () => { throw new Error('ECONNREFUSED'); } });
  const out = await svc.lookup({ eva: '8000261' });
  assert.equal(out.illustrative, true);
  assert.match(out.fallbackFrom, /ECONNREFUSED/);
});
