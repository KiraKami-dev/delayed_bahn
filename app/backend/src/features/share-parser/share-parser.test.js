// Offline tests for the DB share-text grammar and station resolution.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { tokenize, parseConnections, pickFirstComplete, splitLines, berlinIso } from './grammar.js';
import { normaliseName, createStationResolver } from './stations.js';
import { createShareParserService, registerRoutes } from './routes/share-parser.js';
import { Router } from '../../server.js';

const fx = (name) => readFileSync(new URL(`./fixtures/share-texts/${name}`, import.meta.url), 'utf8');
const NOW = () => new Date('2026-09-12T20:00:00Z');
const svc = () => createShareParserService({ env: {}, now: NOW });

test('normaliseName folds umlauts, Hauptbahnhof and punctuation', () => {
  assert.equal(normaliseName('Nürnberg Hbf'), 'nuernberg hbf');
  assert.equal(normaliseName('Nuernberg Hauptbahnhof'), 'nuernberg hbf');
  assert.equal(normaliseName('Frankfurt (Main) Hbf'), 'frankfurt main hbf');
  assert.equal(normaliseName('Zürich HB'), 'zuerich hb');
});

test('station resolver: local table, aliases, loose match, unknown keeps the name', async () => {
  const r = createStationResolver({ env: {} });
  assert.equal((await r.resolve('Nürnberg Hbf')).evaNumber, '8000284');
  assert.equal((await r.resolve('Munich Central Station')).evaNumber, '8000261');
  assert.equal((await r.resolve('Frankfurt (Main) Hauptbahnhof')).evaNumber, '8000105');
  assert.equal((await r.resolve('Zuerich HB')).evaNumber, '8503000');
  assert.deepEqual(await r.resolve('Kleinkleckersdorf'), { evaNumber: '', name: 'Kleinkleckersdorf' });
  assert.equal(typeof (await r.resolve('München Hbf')).lat, 'number');
});

test('station resolver uses the DB Timetables API when creds exist', async () => {
  const calls = [];
  const fetchImpl = async (url) => {
    calls.push(url);
    if (url.includes('/timetables/')) return { ok: true, text: async () => '<stations><station p="true" meta="" name="Kleinkleckersdorf" eva="8001234" ds100="NKL"/></stations>' };
    return { ok: false, status: 404 };
  };
  const r = createStationResolver({ env: { DB_CLIENT_ID: 'id', DB_API_KEY: 'key' }, fetchImpl });
  const s = await r.resolve('Kleinkleckersdorf');
  assert.deepEqual(s, { evaNumber: '8001234', name: 'Kleinkleckersdorf' });
  await r.resolve('Kleinkleckersdorf');
  assert.equal(calls.filter((url) => url.includes('/timetables/')).length, 1, 'cached');
  assert.match(calls[0], /timetables\/v1\/station\/Kleinkleckersdorf/);
});

test('station resolver fills coordinates from RIS::Stations, else OpenStreetMap', async () => {
  const calls = [];
  const resolverWith = (ris) => createStationResolver({
    env: { DB_CLIENT_ID: 'id', DB_API_KEY: 'key' },
    fetchImpl: async (url) => {
      calls.push(url);
      if (url.includes('/timetables/')) return { ok: true, text: async () => '<stations><station name="Kleinkleckersdorf" eva="8001234"/></stations>' };
      if (url.includes('/ris-stations/')) return ris;
      return { ok: true, json: async () => ({ elements: [{ type: 'node', lat: 48.5, lon: 10.5 }] }) };
    },
  });
  const fromRis = await resolverWith({ ok: true, status: 200, json: async () => ({ stopPlaces: [{ position: { latitude: 49.1, longitude: 11.2 } }] }) }).resolve('Kleinkleckersdorf');
  assert.deepEqual(fromRis, { evaNumber: '8001234', name: 'Kleinkleckersdorf', lat: 49.1, lon: 11.2 });

  const r = resolverWith({ ok: false, status: 401 });
  assert.deepEqual(await r.resolve('Kleinkleckersdorf'), { evaNumber: '8001234', name: 'Kleinkleckersdorf', lat: 48.5, lon: 10.5 });
  assert.match(calls.at(-1), /uic_ref/);
  calls.length = 0;
  await r.resolve('Kleinkleckersdorf');
  assert.deepEqual(calls, [], 'station and coordinates cached');
});

test('tokenizer classifies the real sample line by line', () => {
  const types = tokenize(fx('real-sample-en.txt')).map((t) => t.type);
  assert.deepEqual(types, ['HEADER', 'DATE', 'TRAIN', 'DIRECTION', 'STOP', 'STOP', 'URL']);
  const toks = tokenize(fx('real-sample-en.txt'));
  assert.deepEqual(toks[2], { type: 'TRAIN', trainId: 'RB 16', trainNumber: '59143' });
  assert.equal(toks[4].tag, 'dep'); assert.equal(toks[4].station, 'Nürnberg Hbf'); assert.equal(toks[4].platform, 'Platform 5 C-F');
  assert.equal(toks[5].tag, 'arr'); assert.equal(toks[5].station, 'München Hbf');
  assert.equal(toks[6].vbid, 'e6285f4d-26a0-45db-a595-f36ddbb4ff20');
});

test('splitLines restores newlines lost in a chat paste', () => {
  const flat = 'Nürnberg Hbf → München HbfSun 13.09.2026RB16 (59143)To München HbfFrom 04:34 Nürnberg Hbf, Platform 5 C-FTo 07:25 München Hbf, Platform 21View journey: https://int.bahn.de/en/buchung/start?vbid=e6285f4d-26a0-45db-a595-f36ddbb4ff20';
  const lines = splitLines(flat.replace(/HbfSun/, 'Hbf Sun').replace(/2026RB16/, '2026 RB16').replace(/HbfFrom/, 'Hbf From').replace(/C-FTo/, 'C-F To').replace(/21View/, '21 View'));
  assert.ok(lines.some((l) => /^From 04:34/.test(l)));
  assert.ok(lines.some((l) => /^To 07:25/.test(l)));
  assert.ok(lines.some((l) => /^RB16/.test(l)));
});

test('real sample parses to one RB 16 leg with EVA numbers and Berlin offset', async () => {
  const j = await svc().parse(fx('real-sample-en.txt'));
  assert.equal(j.source, 'db-share');
  assert.match(j.id, /^jrn_[0-9a-f]{10}$/);
  assert.equal(j.legs.length, 1);
  const l = j.legs[0];
  assert.equal(l.trainId, 'RB 16');
  assert.equal(l.trainNumber, '59143');
  assert.equal(l.from.evaNumber, '8000284');
  assert.equal(l.to.evaNumber, '8000261');
  assert.equal(l.plannedDeparture, '2026-09-13T04:34:00+02:00');
  assert.equal(l.plannedArrival, '2026-09-13T07:25:00+02:00');
  assert.equal(l.transferMinutes, undefined);
  assert.equal(typeof l.from.lat, 'number');
  assert.match(j.url, /vbid=e6285f4d/);
});

test('german variant parses the same', async () => {
  const j = await svc().parse(fx('german-sample.txt'));
  assert.equal(j.legs.length, 1);
  assert.equal(j.legs[0].trainId, 'RB 16');
  assert.equal(j.legs[0].plannedDeparture, '2026-09-13T04:34:00+02:00');
  assert.equal(j.legs[0].to.name, 'München Hbf');
});

test('two legs: transfer derived from the times', async () => {
  const j = await svc().parse(fx('two-legs-en.txt'));
  assert.equal(j.legs.length, 2);
  assert.equal(j.legs[0].transferMinutes, 16);
  assert.equal(j.legs[1].trainId, 'S 8');
  assert.equal(j.legs[1].to.evaNumber, '8004167');
  assert.equal(j.legs[1].transferMinutes, undefined);
});

test('two connections: the incomplete first one is skipped, explicit change line wins', async () => {
  const conns = parseConnections(tokenize(fx('two-connections.txt')));
  assert.equal(conns.length, 2);
  assert.equal(conns[0].complete, false);
  const chosen = pickFirstComplete(conns);
  assert.equal(chosen.legs.length, 2);
  const j = await svc().parse(fx('two-connections.txt'));
  assert.equal(j.legs[0].trainId, 'RB 16');
  assert.equal(j.legs[0].transferMinutes, 16);
});

test('url-only text -> 422 without the resolver, journey with it', async () => {
  await assert.rejects(() => svc().parse(fx('url-only.txt')), (e) => e.status === 422 && e.details.resolverEnabled === false);
  const fetchImpl = async () => ({ ok: true, json: async () => ({ verbindungen: [{ verbindungsAbschnitte: [
    { verkehrsmittel: { typ: 'REGIONAL', name: 'RB 16' }, abfahrtsOrt: 'Nürnberg Hbf', abfahrtsOrtExtId: '8000284', ankunftsOrt: 'München Hbf', ankunftsOrtExtId: '8000261', abfahrtsZeitpunkt: '2026-09-13T04:34:00', ankunftsZeitpunkt: '2026-09-13T07:25:00' },
    { verkehrsmittel: { typ: 'WALK' } },
  ] }] }) });
  const j = await createShareParserService({ env: { BAHN_VBID_RESOLVER: '1' }, fetchImpl, now: NOW }).parse(fx('url-only.txt'));
  assert.equal(j.legs.length, 1);
  assert.equal(j.legs[0].from.evaNumber, '8000284');
});

test('junk -> 400; missing text -> 400; date defaults to today in Berlin', async () => {
  await assert.rejects(() => svc().parse('hello'), (e) => e.status === 400 && e.details.connectionsSeen === 0);
  const router = new Router();
  registerRoutes(router, { env: {}, now: NOW });
  const m = router.match('POST', '/api/journeys/parse');
  await assert.rejects(() => m.handler({ params: {}, query: new URLSearchParams(), body: {} }), (e) => e.status === 400);
  const j = await m.handler({ params: {}, query: new URLSearchParams(), body: { text: 'RB16 (59143)\nFrom 04:34 Nürnberg Hbf\nTo 07:25 München Hbf' } });
  assert.equal(j.legs[0].plannedDeparture, '2026-09-12T04:34:00+02:00');
  assert.equal(berlinIso({ y: 2026, m: 1, d: 15 }, 8, 5), '2026-01-15T08:05:00+01:00');
});

test('overnight leg rolls the arrival to the next day', async () => {
  const j = await svc().parse('Sun 13.09.2026\nICE 1005\nFrom 23:10 Berlin Hbf, Platform 12\nTo 01:30 München Hbf, Platform 20');
  assert.equal(j.legs[0].plannedDeparture, '2026-09-13T23:10:00+02:00');
  assert.equal(j.legs[0].plannedArrival, '2026-09-14T01:30:00+02:00');
});
