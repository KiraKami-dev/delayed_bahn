// Ports the Python connection tests and smokes the prediction service offline.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { changeProbability, journeyProbability, point, forecast, quantile, onTimeProbability, binned } from './connection.js';
import { createMockBackend, geometric, trainClass } from './backends/mock.js';
import { createPredictionService, registerRoutes, isClassAverage } from './routes/delay-prediction.js';
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

const spike = (m) => { const probs = new Array(1000).fill(0); probs[m] = 1; return probs; };
const tripModelReply = () => ({
  modelId: 'trip-model', confidence: 'low',
  legs: [
    { arrival: { probs: spike(2), pCancel: 0 }, reasoning: 'Live forecast.', sources: ['trip-model (live data)'], confidence: 'high' },
    { arrival: { probs: spike(1), pCancel: 0.02 }, reasoning: 'No recorded trip matches S 8 arriving at the airport at the planned time, so this is the average of recorded S arrivals, not a forecast. Live data could not be used.', sources: ['class average of the recorded trips (no matching record)'], confidence: 'low' },
  ],
});

test('a class-average leg is recognised', () => {
  assert.equal(isClassAverage(tripModelReply().legs[1]), true);
  assert.equal(isClassAverage(tripModelReply().legs[0]), false);
});

test('the route model complements the legs the trip model could only average', async () => {
  const calls = [];
  const fetchImpl = async (url, init) => {
    calls.push(String(url));
    if (String(url).includes('route')) {
      const body = JSON.parse(init.body);
      assert.equal(body.legs.length, 1, 'only the averaged leg goes to the route model');
      assert.equal(body.legs[0].trainId, seed.legs[1].trainId);
      return { ok: true, json: async () => ({ modelId: 'route-model', confidence: 'medium', legs: [{ arrival: { probs: spike(7), pCancel: 0.01 }, reasoning: 'Fine-tuned model forecast for S -> airport.', sources: ['route-model (model forecast)'], confidence: 'medium', origin: 'model forecast' }] }) };
    }
    return { ok: true, json: async () => tripModelReply() };
  };
  const svc = createPredictionService({ env: { PREDICT_URL: 'http://trip/', PREDICT_FALLBACK_URL: 'http://route/predict' }, fetchImpl });
  const p = await svc.predict(seed);
  assert.equal(calls.length, 2);
  assert.equal(p.modelId, 'trip-model + route-model (1 leg)');
  assert.deepEqual(p.complementedLegs, [1]);
  assert.equal(p.legs[0].expectedDelayMinutes.value, 2, 'the live leg is untouched');
  assert.equal(p.legs[0].expectedDelayMinutes.confidence, 'high');
  assert.equal(p.legs[1].expectedDelayMinutes.value, 7, 'the averaged leg now carries the route model forecast');
  assert.equal(p.legs[1].complementedBy, 'route-model');
  assert.match(p.legs[1].expectedDelayMinutes.reasoning, /Fine-tuned model forecast for S -> airport\. Used because the trip model had no matching trip: No recorded trip matches/);
  assert.ok(p.legs[1].expectedDelayMinutes.sources.includes('route model instead of the trip model\'s class average'));
  assert.equal(p.planFailProbability.confidence, 'medium');
});

test('without a class-average leg the route model is not asked', async () => {
  const calls = [];
  const fetchImpl = async (url) => { calls.push(String(url)); return { ok: true, json: async () => ({ ...tripModelReply(), legs: [tripModelReply().legs[0], tripModelReply().legs[0]] }) }; };
  const svc = createPredictionService({ env: { PREDICT_URL: 'http://trip/', PREDICT_FALLBACK_URL: 'http://route/predict' }, fetchImpl });
  const p = await svc.predict(seed);
  assert.equal(calls.length, 1);
  assert.equal(p.modelId, 'trip-model');
  assert.equal(p.complementedLegs, undefined);
});

test('when the route model is down the class average stays and says so', async () => {
  const fetchImpl = async (url) => {
    if (String(url).includes('route')) throw new Error('ECONNREFUSED');
    return { ok: true, json: async () => tripModelReply() };
  };
  const svc = createPredictionService({ env: { PREDICT_URL: 'http://trip/', PREDICT_FALLBACK_URL: 'http://route/predict' }, fetchImpl });
  const p = await svc.predict(seed);
  assert.equal(p.modelId, 'trip-model');
  assert.equal(p.legs[1].expectedDelayMinutes.value, 1);
  assert.ok(p.legs[1].expectedDelayMinutes.sources.some((s) => /route model unavailable.*ECONNREFUSED/.test(s)));
});
