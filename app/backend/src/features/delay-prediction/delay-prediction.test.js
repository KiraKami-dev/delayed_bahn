// Ports the Python connection tests and smokes the prediction service offline.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { changeProbability, journeyProbability, point, forecast, quantile, onTimeProbability, binned } from './connection.js';
import { createMockBackend, geometric, trainClass } from './backends/mock.js';
import { createPredictionService, registerRoutes } from './routes/delay-prediction.js';
import { Router } from '../../server.js';

const seed = JSON.parse(readFileSync(new URL('../pwa-shell/fixtures/seed-journey.json', import.meta.url), 'utf8'));
const near = (a, b, eps = 1e-9) => assert.ok(Math.abs(a - b) < eps, `${a} != ${b}`);

test('point masses: eight minutes of buffer, four to change', () => {
  assert.equal(changeProbability(point(5), point(0), 8, 4), 0);
  assert.equal(changeProbability(point(3), point(0), 8, 4), 1);
  assert.equal(changeProbability(point(5), point(2), 8, 4), 1);
  assert.equal(changeProbability(point(4), point(0), 8, 4), 1);
});

test('cancellations multiply', () => {
  near(changeProbability(point(0, 1000, 0.1), point(0, 1000, 0.2), 8, 4), 0.9 * 0.8);
});

test('tail-sum matches the brute-force double sum for geometric-ish delays', () => {
  const k = Array.from({ length: 200 }, (_, i) => i);
  const a = forecast(k.map((x) => Math.exp(-x / 6)));
  const d = forecast(k.map((x) => Math.exp(-x / 3)));
  const exact = changeProbability(a, d, 7, 3);
  const sa = a.probs.reduce((x, y) => x + y, 0), sd = d.probs.reduce((x, y) => x + y, 0);
  let brute = 0;
  for (let i = 0; i < 200; i++) for (let j = 0; j < 200; j++) if (i - j <= 4) brute += (a.probs[i] / sa) * (d.probs[j] / sd);
  near(exact, brute, 1e-9);
});

test('journey chains changes and a deadline', () => {
  const final = forecast([0.5, 0, 0, 0.5]);
  const r = journeyProbability([[point(1), point(0), 6, 3], [point(2), point(0), 6, 3]], final, 2);
  assert.deepEqual(r.changeProbabilities, [1, 1]);
  near(r.planSuccess, 0.5);
  near(r.planFail, 0.5);
});

test('quantile, on-time and bins on a geometric prior', () => {
  const f = forecast(geometric(8), 0.02);
  assert.equal(quantile(f, 0.5), 8);
  assert.ok(quantile(f, 0.1) < 8 && quantile(f, 0.9) > 8);
  assert.ok(onTimeProbability(f) > 0 && onTimeProbability(f) < 1);
  const b = binned(f);
  assert.equal(b.bins.length, 5);
  near(b.probs.reduce((x, y) => x + y, 0), 1, 1e-9);
  assert.equal(trainClass('RB 16'), 'RB');
  assert.equal(trainClass('ICE1005'), 'ICE');
});

test('mock prior is deterministic and shaped for the contract', async () => {
  const svc = createPredictionService({ env: {} });
  const p1 = await svc.predict(seed);
  const p2 = await svc.predict(seed);
  assert.deepEqual(p1, p2);
  assert.equal(p1.journeyId, seed.id);
  assert.equal(p1.modelId, 'mock-prior-v1');
  assert.equal(p1.legs.length, 2);
  assert.ok(p1.planFailProbability.value > 0 && p1.planFailProbability.value < 1);
  assert.equal(p1.legs[1].missProbability.value, 0);
  assert.ok(p1.legs[0].missProbability.value > 0);
  assert.equal(p1.legs[0].distribution.bins.length, 5);
  assert.ok(p1.legs[0].quantiles.p10 <= p1.legs[0].quantiles.p50);
  assert.match(p1.legs[0].expectedDelayMinutes.reasoning, /about \+\d+ min, likely \d+ to \d+ min, \d+% chance of arriving on time/);
  assert.equal(p1.planFailProbability.confidence, 'low');
});

test('http backend falls back to the mock and says so', async () => {
  const fetchImpl = async () => { throw new Error('ECONNREFUSED'); };
  const svc = createPredictionService({ env: { PREDICT_URL: 'http://127.0.0.1:9/predict' }, fetchImpl });
  const p = await svc.predict(seed);
  assert.equal(p.modelId, 'mock-prior-v1');
  assert.match(p.fallbackFrom, /ECONNREFUSED/);
  assert.ok(p.legs[0].expectedDelayMinutes.sources.some((s) => s.startsWith('fallback')));
});

test('http backend reply is used when valid', async () => {
  const probs = new Array(1000).fill(0); probs[3] = 1;
  const fetchImpl = async () => ({ ok: true, json: async () => ({ modelId: 'opentslm-test', legs: seed.legs.map(() => ({ arrival: { probs, pCancel: 0 } })) }) });
  const svc = createPredictionService({ env: { PREDICT_URL: 'http://model/predict' }, fetchImpl });
  const p = await svc.predict(seed);
  assert.equal(p.modelId, 'opentslm-test');
  assert.equal(p.legs[0].expectedDelayMinutes.value, 3);
  assert.equal(p.planFailProbability.confidence, 'medium');
  assert.equal(p.planFailProbability.value, 0); // 3 min late, 16 min buffer, 5 min transfer
});

test('route validates the body', async () => {
  const router = new Router();
  registerRoutes(router, { env: {} });
  const m = router.match('POST', '/api/predict');
  await assert.rejects(() => m.handler({ params: {}, query: new URLSearchParams(), body: {} }), (e) => e.status === 400);
  const ok = await m.handler({ params: {}, query: new URLSearchParams(), body: seed });
  assert.equal(ok.legs.length, 2);
  const mock = createMockBackend();
  assert.equal((await mock.forecast(seed)).legs.length, 2);
});
