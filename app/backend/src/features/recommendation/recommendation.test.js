// Offline tests: recommendation rules, leave-home-by, re-route options, causes lookup.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createPredictionService } from '../delay-prediction/routes/delay-prediction.js';
import { createRecommendationService, registerRoutes } from './routes/recommendation.js';
import { createCausesService, registerRoutes as registerCauses } from '../causes/routes/causes.js';
import { Router } from '../../server.js';

const seed = JSON.parse(readFileSync(new URL('../pwa-shell/fixtures/seed-journey.json', import.meta.url), 'utf8'));
const predict = createPredictionService({ env: {} });
const rec = createRecommendationService({ env: {}, predict });

test('seed journey gets a non-good verdict with actionable advice', async () => {
  const prediction = await predict.predict(seed);
  const r = await rec.recommend({ journey: seed, prediction, doorToStationMin: 20 });
  assert.ok(['add-buffer', 'take-alternative'].includes(r.verdict), r.verdict);
  assert.ok(r.advice.value.length > 40);
  assert.equal(r.advice.confidence, 'low');
  assert.ok(r.advice.sources.includes('recommendation-rules v1'));
  assert.ok(r.alternative?.legs?.length >= 1);
  assert.match(r.leaveHomeBy, /^2026-09-13T\d{2}:\d{2}:00\+02:00$/);
  assert.ok(Date.parse(r.leaveHomeBy) < Date.parse(r.chosenDeparture));
  assert.equal(Math.round((Date.parse(r.chosenDeparture) - Date.parse(r.leaveHomeBy)) / 60000), 25);
  assert.match(r.advice.value, /Leave home by \d{2}:\d{2}/);
});

test('generous transfers are good; hand-made low risk is good', async () => {
  const relaxed = { ...seed, id: 'relaxed', legs: seed.legs.map((l, i) => (i === 0 ? { ...l, transferMinutes: 60 } : l)) };
  const p = await predict.predict(relaxed);
  const r = await rec.recommend({ journey: relaxed, prediction: p });
  assert.equal(r.verdict, 'good');
  assert.equal(r.leaveHomeBy, undefined);
  const fake = { ...p, planFailProbability: { ...p.planFailProbability, value: 0.05 } };
  assert.equal((await rec.recommend({ journey: seed, prediction: fake })).verdict, 'good');
});

test('take-alternative uses the fixture for the seed route when no buffer helps', async () => {
  const p = await predict.predict(seed);
  const stubborn = { ...p, planFailProbability: { ...p.planFailProbability, value: 0.9 } };
  const strict = await rec.recommend({ journey: seed, prediction: stubborn, acceptableRisk: 0.0001 });
  assert.equal(strict.verdict, 'take-alternative');
  assert.equal(strict.alternative.id, 'seed-nue-muc-airport-alt');
  assert.match(strict.advice.value, /Leave 60 min earlier on RB 16 at 03:34/);
});

test('canned path without a prediction service still answers', async () => {
  const canned = createRecommendationService({ env: {} });
  const p = await predict.predict(seed);
  const r = await canned.recommend({ journey: seed, prediction: { ...p, planFailProbability: { ...p.planFailProbability, value: 0.5 } } });
  assert.equal(r.verdict, 'take-alternative');
  assert.equal(r.alternative.legs.length, 2);
});

test('reroute lists next connections from the missed station, scored and sorted', async () => {
  const r = await rec.reroute({ journey: seed, missedLegIndex: 0 });
  assert.equal(r.station.evaNumber, '8000261');
  assert.equal(r.options.length, 3);
  assert.equal(r.options[0].arrivalDelayMinutes, 10);
  assert.ok(r.options.every((o) => typeof o.planFailProbability.value === 'number' && o.journey.legs.length === 1));
  assert.equal(r.best.label, 'Next S 8, 10 min later');
  assert.match(r.advice, /You missed S 8 at München Hbf/);
  const generic = await rec.reroute({ journey: { ...seed, legs: [{ ...seed.legs[0], to: { evaNumber: '8000262', name: 'München Ost' } }, { ...seed.legs[1], from: { evaNumber: '8000262', name: 'München Ost' } }] }, missedLegIndex: 0 });
  assert.equal(generic.options.length, 3);
  assert.match(generic.source, /synthesised/);
  await assert.rejects(() => rec.reroute({ journey: seed, missedLegIndex: 1 }), (e) => e.status === 400);
});

test('routes validate bodies', async () => {
  const router = new Router();
  registerRoutes(router, { env: {}, predict });
  const m = router.match('POST', '/api/recommend');
  await assert.rejects(() => m.handler({ params: {}, query: new URLSearchParams(), body: { journey: seed } }), (e) => e.status === 400);
  assert.ok(router.match('POST', '/api/reroute'));
});

test('causes lookup by eva, by station name, and default fallback', () => {
  const svc = createCausesService({ env: {} });
  const muc = svc.lookup({ eva: '8000261' });
  assert.equal(muc.station.name, 'München Hbf');
  assert.equal(muc.matched, true);
  const sum = Object.values(muc.families).reduce((a, b) => a + b, 0);
  assert.ok(Math.abs(sum - 1) < 0.01, `families sum ${sum}`);
  assert.equal(muc.top[0].code, 43);
  assert.equal(muc.sparkline7d.length, 7);
  const byName = svc.lookup({ station: 'Nürnberg Hbf' });
  assert.equal(byName.station.evaNumber, '8000284');
  const unknown = svc.lookup({ eva: '8999999' });
  assert.equal(unknown.matched, false);
  assert.ok(unknown.families.unattributed > 0.5);
  assert.throws(() => svc.lookup({}), (e) => e.status === 400);
  const router = new Router();
  registerCauses(router, { env: {} });
  assert.ok(router.match('GET', '/api/causes'));
});
