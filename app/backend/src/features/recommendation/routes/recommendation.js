// recommendation: POST /api/recommend  { journey, prediction, doorToStationMin?, acceptableRisk? }
//   -> Recommendation (contract) + additive leaveHomeBy / chosenDeparture / riskAfter
// and POST /api/reroute  { journey, missedLegIndex } -> next connections from
// the station where the change broke, each scored with the prediction chain.
// Advice speaks like a weather forecast: not "it will rain", but "take an umbrella".
import { readFileSync } from 'node:fs';

const fail = (status, message, details) => Object.assign(new Error(message), { status, details });
const pct = (x) => `${Math.round(x * 100)}%`;
const r3 = (x) => Math.round(x * 1000) / 1000;
const GOOD_THRESHOLD = 0.15;
const BUFFER_STEPS = [5, 10, 15, 20, 25, 30];

const BERLIN_TIME = new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Berlin' });
const hhmm = (iso) => BERLIN_TIME.format(new Date(iso));
const shiftIso = (iso, minutes) => {
  const d = new Date(new Date(iso).getTime() + minutes * 60000);
  const offset = /([+-]\d{2}:\d{2}|Z)$/.exec(iso)?.[1] || 'Z';
  if (offset === 'Z') return d.toISOString();
  const sign = offset[0] === '-' ? -1 : 1;
  const [oh, om] = offset.slice(1).split(':').map(Number);
  const local = new Date(d.getTime() + sign * (oh * 60 + om) * 60000);
  return local.toISOString().slice(0, 19) + offset;
};
const routeKey = (journey) => `${journey.legs[0]?.from?.evaNumber}->${journey.legs.at(-1)?.to?.evaNumber}`;

function loadJson(rel) {
  return JSON.parse(readFileSync(new URL(rel, import.meta.url), 'utf8'));
}

export function createRecommendationService({ env = process.env, predict, alternatives, reroutes, minTransfer } = {}) {
  const alts = alternatives ?? loadJson('../fixtures/alternatives.json');
  const rr = reroutes ?? loadJson('../fixtures/reroute.json');
  const minT = minTransfer ?? predict?.minTransfer ?? Number(env.MIN_TRANSFER_MINUTES || 5);

  function validate(journey, prediction) {
    if (!journey?.legs?.length) throw fail(400, 'Body must include journey.legs');
    if (!prediction?.legs?.length || typeof prediction?.planFailProbability?.value !== 'number') throw fail(400, 'Body must include prediction.legs and prediction.planFailProbability');
  }

  function weakestTransfer(prediction) {
    let idx = -1, worst = -1;
    prediction.legs.slice(0, -1).forEach((l, i) => { if (l.missProbability.value > worst) { worst = l.missProbability.value; idx = i; } });
    return idx;
  }

  /** Shift every leg up to and including `idx` earlier so the transfer at idx grows by `extra` minutes. */
  function withBuffer(journey, idx, extra) {
    const legs = journey.legs.map((l, i) => {
      if (i > idx) return { ...l };
      return { ...l, plannedDeparture: shiftIso(l.plannedDeparture, -extra), plannedArrival: shiftIso(l.plannedArrival, -extra), transferMinutes: i === idx ? (l.transferMinutes ?? 0) + extra : l.transferMinutes };
    });
    return { ...journey, id: `${journey.id}-buf${extra}`, legs, source: 'manual' };
  }

  function synthesisedAlternative(journey, minutesEarlier = 30) {
    return {
      ...journey,
      id: `${journey.id}-alt`,
      source: 'manual',
      legs: journey.legs.map((l, i) => ({
        ...l,
        plannedDeparture: shiftIso(l.plannedDeparture, -minutesEarlier),
        plannedArrival: shiftIso(l.plannedArrival, -minutesEarlier),
        transferMinutes: i < journey.legs.length - 1 ? (l.transferMinutes ?? 0) + (i === 0 ? 0 : 0) : undefined,
      })),
    };
  }

  return {
    async recommend({ journey, prediction, doorToStationMin, acceptableRisk }) {
      validate(journey, prediction);
      const pf = prediction.planFailProbability.value;
      const risk = typeof acceptableRisk === 'number' ? acceptableRisk : GOOD_THRESHOLD;
      const sources = [...(prediction.planFailProbability.sources || []), 'recommendation-rules v1'];
      const confidence = prediction.planFailProbability.confidence || 'low';
      const dest = journey.legs.at(-1).to?.name || 'your destination';

      let rec;
      if (pf < risk) {
        rec = {
          verdict: 'good',
          advice: {
            value: `Clear skies: about ${pct(pf)} chance this plan breaks. Keep it — no umbrella needed. You arrive at ${dest} around ${hhmm(journey.legs.at(-1).plannedArrival)}.`,
            reasoning: `Plan-fail probability ${pct(pf)} is below the ${pct(risk)} threshold you accept.`,
            sources, confidence,
          },
          chosenDeparture: journey.legs[0].plannedDeparture,
          riskAfter: r3(pf),
        };
      } else {
        const idx = weakestTransfer(prediction);
        const weak = idx >= 0 ? prediction.legs[idx] : null;
        const station = idx >= 0 ? journey.legs[idx].to?.name || 'the change' : dest;
        let found = null;
        if (predict && idx >= 0) {
          const forecasts = await predict.forecast(journey);
          for (const b of BUFFER_STEPS) {
            const j2 = withBuffer(journey, idx, b);
            const p2 = predict.chain(j2, forecasts).planFailProbability.value;
            if (p2 < risk) { found = { b, p2, j2 }; break; }
          }
        }
        if (found) {
          rec = {
            verdict: 'add-buffer',
            bufferMinutes: found.b,
            advice: {
              value: `Showers likely at ${station}: ${journey.legs[idx].trainId} tends to arrive ~${weak.expectedDelayMinutes.value} min late and ${journey.legs[idx].transferMinutes ?? '?'} min to change is tight (${pct(weak.missProbability.value)} chance you miss it). Take the connection ${found.b} min earlier and the risk drops from ${pct(pf)} to ${pct(found.p2)}.`,
              reasoning: `Weakest transfer is at ${station} (${pct(weak.missProbability.value)}). Re-chaining with +${found.b} min there gives ${pct(found.p2)} < ${pct(risk)}.`,
              sources, confidence,
            },
            alternative: found.j2,
            chosenDeparture: found.j2.legs[0].plannedDeparture,
            riskAfter: r3(found.p2),
          };
        } else {
          const alternative = alts[routeKey(journey)] ? structuredClone(alts[routeKey(journey)]) : synthesisedAlternative(journey, 30);
          let p3 = null;
          if (predict) { try { p3 = (await predict.predict(alternative)).planFailProbability.value; } catch { p3 = null; } }
          const earlier = Math.round((Date.parse(journey.legs[0].plannedDeparture) - Date.parse(alternative.legs[0].plannedDeparture)) / 60000);
          rec = {
            verdict: 'take-alternative',
            alternative,
            advice: {
              value: `Storm warning: ${pct(pf)} chance you miss a connection, worst at ${station}${weak ? ` (${pct(weak.missProbability.value)})` : ''}. Leave ${earlier} min earlier on ${alternative.legs[0].trainId} at ${hhmm(alternative.legs[0].plannedDeparture)}: you reach ${dest} at ${hhmm(alternative.legs.at(-1).plannedArrival)}${p3 !== null ? ` with ${pct(p3)} risk` : ''} — comfortable, not a sprint with luggage.`,
              reasoning: `No buffer up to 30 min at ${station} brings the risk under ${pct(risk)}, so the earlier connection is the umbrella.`,
              sources, confidence,
            },
            chosenDeparture: alternative.legs[0].plannedDeparture,
            riskAfter: p3 !== null ? r3(p3) : undefined,
          };
        }
      }

      if (typeof doorToStationMin === 'number' && doorToStationMin >= 0) {
        rec.leaveHomeBy = shiftIso(rec.chosenDeparture, -(doorToStationMin + 5));
        rec.advice.value += ` Leave home by ${hhmm(rec.leaveHomeBy)} (${doorToStationMin} min to the station + 5 min on the platform).`;
      }
      return rec;
    },

    async reroute({ journey, missedLegIndex }) {
      if (!journey?.legs?.length) throw fail(400, 'Body must include journey.legs');
      const idx = Number(missedLegIndex);
      if (!Number.isInteger(idx) || idx < 0 || idx >= journey.legs.length - 1) throw fail(400, 'missedLegIndex must point at a leg that has a following connection');
      const station = journey.legs[idx].to;
      const remaining = journey.legs.slice(idx + 1);
      const key = `${station?.evaNumber}->${journey.legs.at(-1)?.to?.evaNumber}`;
      const candidates = rr[key]
        ? structuredClone(rr[key])
        : [10, 20, 30].map((m) => ({
          label: `Same trains, ${m} min later`,
          legs: remaining.map((l) => ({ ...l, plannedDeparture: shiftIso(l.plannedDeparture, m), plannedArrival: shiftIso(l.plannedArrival, m) })),
        }));
      const plannedArrival = Date.parse(journey.legs.at(-1).plannedArrival);
      const options = [];
      for (const c of candidates) {
        const j = { id: `${journey.id}-reroute-${options.length + 1}`, source: 'manual', legs: c.legs };
        let pfp = { value: 0, reasoning: 'No prediction service available.', sources: ['reroute fixture'], confidence: 'low' };
        if (predict) { try { pfp = (await predict.predict(j)).planFailProbability; } catch { /* keep default */ } }
        options.push({
          label: c.label,
          journey: j,
          planFailProbability: pfp,
          arrivalDelayMinutes: Math.round((Date.parse(c.legs.at(-1).plannedArrival) - plannedArrival) / 60000),
          departure: c.legs[0].plannedDeparture,
        });
      }
      options.sort((a, b) => a.arrivalDelayMinutes - b.arrivalDelayMinutes || a.planFailProbability.value - b.planFailProbability.value);
      const best = options[0];
      return {
        station,
        missedLegIndex: idx,
        options,
        best: best ? { label: best.label, journeyId: best.journey.id } : null,
        advice: best
          ? `You missed ${journey.legs[idx + 1].trainId} at ${station?.name}. Best re-route: ${best.label} at ${hhmm(best.departure)} — arrives ${best.arrivalDelayMinutes} min later than planned with ${pct(best.planFailProbability.value)} risk.`
          : 'No re-route found.',
        source: rr[key] ? 'reroute fixture (timetable-shaped)' : 'synthesised: same trains shifted later',
      };
    },
  };
}

export function registerRoutes(router, ctx = {}) {
  const svc = ctx.service || createRecommendationService(ctx);
  router.post('/api/recommend', ({ body }) => svc.recommend(body || {}));
  router.post('/api/reroute', ({ body }) => svc.reroute(body || {}));
  return svc;
}
