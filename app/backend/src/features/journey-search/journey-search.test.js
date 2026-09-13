import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createJourneySearchService, parsePlan, ptToIso, trainLabel, sameStation } from './routes/journey-search.js';

const plan = (station, stops) => `<?xml version='1.0' encoding='UTF-8'?><timetable station='${station}'>${stops.join('')}</timetable>`;
const s = (c, n, { ar, dp, l } = {}) => `<s id="x-${n}"><tl f="F" t="p" o="80" c="${c}" n="${n}"/>${ar ? `<ar pt="${ar.pt}" pp="${ar.pp || '1'}" ${l ? `l="${l}" ` : ''}ppth="${ar.path}"/>` : ''}${dp ? `<dp pt="${dp.pt}" pp="${dp.pp || '2'}" ${l ? `l="${l}" ` : ''}ppth="${dp.path}"/>` : ''}</s>`;
const reply = (status, text) => ({ ok: status < 400, status, text: async () => text });
const env = { DB_CLIENT_ID: 'id', DB_API_KEY: 'key' };

test('ptToIso converts Berlin wall-clock times with the right offset', () => {
  assert.equal(ptToIso('2609130834'), '2026-09-13T08:34:00+02:00');
  assert.equal(ptToIso('2601151205'), '2026-01-15T12:05:00+01:00');
  assert.equal(ptToIso('bogus'), null);
});

test('sameStation tolerates DB sub-station suffixes but not different stations', () => {
  assert.ok(sameStation('München Hbf', 'München Hbf (tief)'));
  assert.ok(sameStation('Berlin Hbf (tief)', 'Berlin Hbf'));
  assert.ok(!sameStation('München Hbf', 'München Ost'));
  assert.ok(!sameStation('Hamburg Hbf', 'Hamburg-Harburg'));
  assert.ok(!sameStation('', 'Berlin Hbf'));
});

test('parsePlan reads trip label, arrival and departure paths', () => {
  const stops = parsePlan(plan('Hamburg Hbf', [s('ICE', '507', { ar: { pt: '2609130830', path: 'Kiel Hbf|Neumünster|Hamburg Dammtor' }, dp: { pt: '2609130834', path: 'Berlin Hbf|Berlin Südkreuz|M&#252;nchen Hbf' } }), s('RE', '11259', { dp: { pt: '2609130821', path: 'Hamburg-Bergedorf' }, l: 'RE7' })]));
  assert.equal(stops.length, 2);
  assert.deepEqual(stops[0].departure.path, ['Berlin Hbf', 'Berlin Südkreuz', 'M&#252;nchen Hbf']);
  assert.equal(stops[0].arrival.iso, '2026-09-13T08:30:00+02:00');
  assert.equal(trainLabel(stops[0]), 'ICE 507');
  assert.equal(trainLabel(stops[1]), 'RE 7');
});

test('search returns direct trains with arrival times from the destination plan', async () => {
  const calls = [];
  const fetchImpl = async (url) => {
    calls.push(String(url));
    const st = /station\/(\d+)$/.exec(String(url));
    if (st) return reply(200, st[1] === '8011160' ? '<stations><station meta="8098160|8089021" name="Berlin Hbf" eva="8011160"/></stations>' : '<stations><station name="Hamburg Hbf" eva="8002549"/></stations>');
    const m = /plan\/(\d+)\/(\d{6})\/(\d{2})$/.exec(String(url));
    if (!m) return reply(404, '');
    if (m[1] === '8002549' && m[3] === '08') return reply(200, plan('Hamburg Hbf', [
      s('ICE', '507', { dp: { pt: '2609130834', pp: '8A-F', path: 'Berlin Hbf|Berlin Südkreuz|München Hbf' } }),
      s('ICE', '507', { dp: { pt: '2609130834', pp: '8A-F', path: 'Berlin Hbf|Berlin Südkreuz|München Hbf' } }), // same train listed under its arrival hour too
      s('ICE', '107', { dp: { pt: '2609130842', path: 'Hamburg-Harburg|Bremen Hbf|Köln Hbf' } }),
      s('RE', '99', { dp: { pt: '2609130810', path: 'Berlin Hbf' } }), // before the requested departure
    ]));
    if (m[1] === '8002549') return reply(200, plan('Hamburg Hbf', []));
    if (m[1] === '8098160' && m[3] === '10') return reply(200, plan('Berlin Hbf (tief)', [
      s('ICE', '507', { ar: { pt: '2609131025', pp: '7', path: 'Hamburg Hbf|Hamburg-Harburg' }, dp: { pt: '2609131028', path: 'Berlin Südkreuz' } }),
    ]));
    return reply(200, plan('Berlin Hbf', []));
  };
  const svc = createJourneySearchService({ env, fetchImpl });
  const out = await svc.search({ from: '8002549', to: '8011160', departure: '2026-09-13T08:20:00+02:00' });
  assert.equal(out.source, 'db-timetables');
  assert.equal(out.journeys.length, 1);
  const [leg] = out.journeys[0].legs;
  assert.equal(leg.trainId, 'ICE 507');
  assert.equal(leg.trainNumber, '507');
  assert.equal(leg.from.name, 'Hamburg Hbf');
  assert.equal(leg.to.evaNumber, '8011160');
  assert.equal(leg.plannedDeparture, '2026-09-13T08:34:00+02:00');
  assert.equal(leg.plannedArrival, '2026-09-13T10:25:00+02:00');
  assert.equal(leg.fromPlatform, '8A-F');
  assert.ok(calls.filter((c) => c.includes('/plan/')).every((c) => /plan\/\d+\/260913\/\d{2}$/.test(c)), calls.join('\n'));
  assert.ok(calls.some((c) => c.includes('/plan/8098160/')), 'meta station plans are scanned');
  assert.ok(out.requests <= 30);
});

test('a second search reuses cached plans and a DB 429 becomes a clear 503', async () => {
  let plans = 0;
  const fetchImpl = async (url) => {
    if (/station\//.test(String(url))) return reply(200, '<stations><station name="X" eva="1"/></stations>');
    plans++;
    return reply(200, plan('x', []));
  };
  const svc = createJourneySearchService({ env, fetchImpl });
  await svc.search({ from: '8002549', to: '8011160', departure: '2026-09-13T08:20:00+02:00' });
  const first = plans;
  await svc.search({ from: '8002549', to: '8011160', departure: '2026-09-13T08:20:00+02:00' });
  assert.equal(plans, first, 'plan files are cached between searches');
  const limited = createJourneySearchService({ env, fetchImpl: async () => reply(429, '') });
  await assert.rejects(limited.search({ from: '8002549', to: '8011160' }), (e) => e.status === 503 && /quota/.test(e.message));
});

test('a station whose local EVA differs from DB is found by name', async () => {
  const calls = [];
  const fetchImpl = async (url) => {
    calls.push(String(url));
    const st = /station\/([^/]+)$/.exec(String(url));
    if (st) {
      const q = decodeURIComponent(st[1]);
      if (q === '8004167') return reply(200, '<stations></stations>');
      if (q === 'München Flughafen Terminal') return reply(200, '<stations><station name="München Flughafen Terminal" eva="8004168"/></stations>');
      return reply(200, `<stations><station name="S" eva="${q}"/></stations>`);
    }
    if (/plan\/8000261\/260913\/08$/.test(String(url))) return reply(200, plan('München Hbf', [s('S', '6934', { dp: { pt: '2609130830', path: 'München Flughafen Besucherpark|München Flughafen Terminal' }, l: 'S8' })]));
    return reply(200, plan('x', []));
  };
  const svc = createJourneySearchService({ env, fetchImpl });
  await svc.search({ from: '8000261', to: '8004167', toName: 'München Flughafen Terminal', departure: '2026-09-13T08:20:00+02:00' });
  assert.ok(calls.some((c) => c.includes('/plan/8004168/')), 'DB EVA for the name is scanned');
  assert.ok(!calls.some((c) => c.includes('/plan/8004167/')), 'an EVA DB does not know is not scanned');
});

test('search refuses to run without credentials and validates input', async () => {
  const svc = createJourneySearchService({ env: {}, fetchImpl: async () => reply(500, '') });
  await assert.rejects(svc.search({ from: '8002549', to: '8011160' }), (e) => e.status === 503);
  const ok = createJourneySearchService({ env, fetchImpl: async () => reply(200, plan('x', [])) });
  await assert.rejects(ok.search({ from: 'Hamburg', to: '8011160' }), (e) => e.status === 400);
  await assert.rejects(ok.search({ from: '8011160', to: '8011160' }), (e) => e.status === 400);
  const empty = await ok.search({ from: '8002549', to: '8011160', departure: '2026-09-13T08:20:00+02:00' });
  assert.deepEqual(empty.journeys, []);
});
