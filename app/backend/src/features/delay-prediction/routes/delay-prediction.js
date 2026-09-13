// delay-prediction: POST /api/predict  Journey -> Prediction (contract) plus
// additive per-leg fields: distribution (binned), quantiles (p10/p50/p90), pCancel.
// Per-leg forecasts come from a backend (mock prior, or the model server via
// PREDICT_URL); chaining across transfers is the JS port of connection.py.
import { changeProbability, journeyProbability, quantile, onTimeProbability, binned, minutesBetween } from '../connection.js';
import { createMockBackend } from '../backends/mock.js';
import { createHttpBackend } from '../backends/http.js';

const fail = (status, message, details) => Object.assign(new Error(message), { status, details });
const pct = (x) => `${Math.round(x * 100)}%`;
const r3 = (x) => Math.round(x * 1000) / 1000;

export function validateJourney(journey) {
  if (!journey || !Array.isArray(journey.legs) || journey.legs.length === 0) throw fail(400, 'Body must be a Journey with at least one leg');
  journey.legs.forEach((leg, i) => {
    for (const k of ['trainId', 'plannedDeparture', 'plannedArrival']) {
      if (typeof leg?.[k] !== 'string' || !leg[k]) throw fail(400, `legs[${i}].${k} is required`);
    }
    if (Number.isNaN(Date.parse(leg.plannedDeparture)) || Number.isNaN(Date.parse(leg.plannedArrival))) throw fail(400, `legs[${i}] has an unparseable planned time`);
  });
}

export function transferBuffer(legs, i) {
  const leg = legs[i];
  if (typeof leg.transferMinutes === 'number') return leg.transferMinutes;
  return minutesBetween(leg.plannedArrival, legs[i + 1].plannedDeparture);
}

/** A leg the trip model could not forecast: it answered with the average of its train class. */
export function isClassAverage(leg) {
  return (leg.sources || []).some((s) => /^class average/i.test(String(s)));
}

const LEVELS = { high: 2, medium: 1, low: 0 };
const lowest = (a, b) => (LEVELS[b] < LEVELS[a] ? b : a);

/**
 * The two model servers complement each other: the trip model (PREDICT_URL) forecasts a train
 * from its live DB position, the route model (PREDICT_FALLBACK_URL) forecasts any recorded
 * service at a station on any date. Legs the trip model could only average go to the route model.
 */
export async function complement(journey, primary, secondary) {
  const idx = primary.legs.map((l, i) => (isClassAverage(l) ? i : -1)).filter((i) => i >= 0);
  if (!idx.length) return primary;
  let second;
  try {
    second = await secondary.forecast({ ...journey, legs: idx.map((i) => journey.legs[i]) });
  } catch (e) {
    for (const i of idx) primary.legs[i].sources = [...primary.legs[i].sources, `route model unavailable for this leg (${e.message})`];
    return primary;
  }
  const legs = primary.legs.map((l) => ({ ...l }));
  idx.forEach((i, k) => {
    const r = second.legs[k];
    if (!r?.arrival?.probs) return;
    const why = String(primary.legs[i].reasoning || '').split(' Live data')[0];
    legs[i] = {
      ...r,
      trainId: journey.legs[i].trainId,
      reasoning: `${r.reasoning || ''} Used because the trip model had no matching trip: ${why}`.trim(),
      sources: [...(r.sources || []), `route model instead of the trip model's class average`],
      complementedBy: second.modelId,
    };
  });
  const replaced = legs.filter((l) => l.complementedBy).length;
  const confidence = legs.reduce((c, l) => (l.confidence ? lowest(c, l.confidence) : c), 'high');
  return {
    ...primary,
    legs,
    confidence: legs.every((l) => l.confidence) ? confidence : lowest(primary.confidence || 'medium', second.confidence || 'medium'),
    modelId: replaced ? `${primary.modelId} + ${second.modelId} (${replaced} leg${replaced === 1 ? '' : 's'})` : primary.modelId,
    ...(replaced ? { complementedLegs: idx.filter((i) => legs[i].complementedBy) } : {}),
  };
}

export function createPredictionService({ env = process.env, backend, fallbackBackend, fetchImpl = fetch } = {}) {
  const mock = createMockBackend();
  const mode = env.PREDICT_BACKEND || (env.PREDICT_URL ? 'http' : 'mock');
  const chosen = backend ?? (mode === 'http'
    ? createHttpBackend({ url: env.PREDICT_URL, fetchImpl, timeoutMs: Number(env.PREDICT_TIMEOUT_MS || 8000) })
    : mock);
  const secondary = fallbackBackend ?? (env.PREDICT_FALLBACK_URL
    ? createHttpBackend({ url: env.PREDICT_FALLBACK_URL, fetchImpl, timeoutMs: Number(env.PREDICT_FALLBACK_TIMEOUT_MS || env.PREDICT_TIMEOUT_MS || 8000) })
    : null);
  const minTransfer = Number(env.MIN_TRANSFER_MINUTES || 5);

  return {
    minTransfer,
    async forecast(journey) {
      validateJourney(journey);
      let f;
      try {
        f = await chosen.forecast(journey);
      } catch (e) {
        if (chosen === mock) throw e;
        f = await mock.forecast(journey);
        f.fallbackFrom = e.message;
        for (const l of f.legs) l.sources = [...l.sources, `fallback: model server unavailable (${e.message})`];
        return f;
      }
      return secondary ? complement(journey, f, secondary) : f;
    },

    /** Pure: journey + per-leg forecasts -> Prediction. Reused by recommendation for what-ifs. */
    chain(journey, forecasts) {
      validateJourney(journey);
      const legs = journey.legs;
      const changes = [];
      const legDelays = legs.map((leg, i) => {
        const f = forecasts.legs[i];
        const p10 = quantile(f.arrival, 0.1), p50 = quantile(f.arrival, 0.5), p90 = quantile(f.arrival, 0.9);
        const onTime = onTimeProbability(f.arrival);
        const headline = `about +${p50} min, likely ${p10} to ${p90} min, ${pct(onTime)} chance of arriving on time`;
        const sources = [...(f.sources || []), forecasts.modelId];

        let miss;
        if (i < legs.length - 1) {
          const next = forecasts.legs[i + 1];
          const buffer = transferBuffer(legs, i);
          const departing = next.departure ?? next.arrival;
          const pMade = changeProbability(f.arrival, departing, buffer, minTransfer);
          changes.push([f.arrival, departing, buffer, minTransfer]);
          const station = leg.to?.name || 'the change station';
          miss = {
            value: r3(1 - pMade),
            reasoning: `${buffer} min planned at ${station}, ${minTransfer} min needed to change → ${Math.floor(buffer - minTransfer)} min of slack. ` +
              `P(${leg.trainId} arrives more than that behind ${legs[i + 1].trainId}) plus cancellations (${pct(f.arrival.pCancel ?? 0)} + ${pct(departing.pCancel ?? 0)}) gives ${pct(1 - pMade)}.`,
            sources,
            confidence: forecasts.confidence,
          };
        } else {
          miss = { value: 0, reasoning: 'Final leg — there is no connection left to miss.', sources, confidence: forecasts.confidence };
        }

        return {
          trainId: leg.trainId,
          expectedDelayMinutes: { value: p50, reasoning: `${headline}. ${f.reasoning || ''}`.trim(), sources, confidence: f.confidence || forecasts.confidence },
          ...(f.complementedBy ? { complementedBy: f.complementedBy } : {}),
          missProbability: miss,
          distribution: binned(f.arrival),
          quantiles: { p10, p50, p90 },
          pCancel: f.arrival.pCancel ?? 0,
          ...(f.generation?.model ? { modelText: f.generation.model, generation: f.generation } : {}),
        };
      });

      const chained = journeyProbability(changes);
      const parts = chained.changeProbabilities.map((p) => `(1−${pct(1 - p)})`).join('·');
      return {
        journeyId: journey.id,
        legs: legDelays,
        planFailProbability: {
          value: r3(chained.planFail),
          reasoning: changes.length
            ? `1 − ${parts} = ${pct(chained.planFail)}. Changes are treated as independent, which is optimistic when one disruption hits both trains; DB holding a connecting train is not modelled.`
            : 'Single leg: the plan only fails if the train is cancelled or very late; no connections to miss.',
          sources: [...new Set(legDelays.flatMap((l) => l.expectedDelayMinutes.sources))],
          confidence: forecasts.confidence,
        },
        modelId: forecasts.modelId,
        ...(forecasts.fallbackFrom ? { fallbackFrom: forecasts.fallbackFrom } : {}),
        ...(forecasts.complementedLegs ? { complementedLegs: forecasts.complementedLegs } : {}),
      };
    },

    async predict(journey) {
      const f = await this.forecast(journey);
      return this.chain(journey, f);
    },
  };
}

// The model's own words for one leg: the model server generates its rationale and answer freely
// (about 360 tokens, some 15 s on a laptop), so the app asks after the forecast, leg by leg.
export async function explainLeg(body, { env = process.env, fetchImpl = fetch } = {}) {
  const leg = body?.leg;
  if (typeof leg?.trainId !== 'string' || !leg.plannedDeparture || !leg.plannedArrival) throw fail(400, 'Body must be { leg } with trainId and planned times');
  if (!env.PREDICT_URL) throw fail(503, 'Explanations need the model server (PREDICT_URL)');
  const base = env.PREDICT_URL.endsWith('/') ? env.PREDICT_URL : `${env.PREDICT_URL}/`;
  const res = await fetchImpl(new URL('explain', base), {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ leg }),
    signal: AbortSignal.timeout(Number(env.EXPLAIN_TIMEOUT_MS || 180000)),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw fail(res.status === 404 ? 404 : 502, data.error || `model server replied ${res.status}`);
  return data;
}

export function registerRoutes(router, ctx = {}) {
  const svc = ctx.service || createPredictionService(ctx);
  router.post('/api/predict', ({ body }) => svc.predict(body));
  router.post('/api/explain', ({ body }) => explainLeg(body, { env: ctx.env }));
  // What the model actually generated for held-out rows (question, its answer, the truth),
  // served by the route server next to its forecasts. Empty when the mock is in use.
  const env = ctx.env || process.env;
  const fetchImpl = ctx.fetchImpl || fetch;
  router.get('/api/predict/generations', async () => {
    if (!env.PREDICT_URL) return { modelId: svc.modelId || 'mock-prior-v1', count: 0, samples: [], note: 'No model server configured; the mock prior generates no text.' };
    const url = new URL(env.PREDICT_URL);
    url.pathname = url.pathname.replace(/\/predict\/?$/, '') + '/generations';
    const res = await fetchImpl(url, { signal: AbortSignal.timeout(Number(env.PREDICT_TIMEOUT_MS || 8000)) });
    if (!res.ok) throw fail(502, `model server replied ${res.status} for generations`);
    return res.json();
  });
  return svc;
}
