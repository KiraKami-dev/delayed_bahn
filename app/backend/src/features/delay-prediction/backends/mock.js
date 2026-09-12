// Deterministic per-leg prior: a geometric delay distribution whose median
// depends on train class, departure hour and leg duration. Stands in for the
// fine-tuned model until PREDICT_URL serves it. No randomness, so the demo is
// byte-identical every run.
import { forecast, minutesBetween } from '../connection.js';

export const MODEL_ID = 'mock-prior-v1';
const LONG_DISTANCE = new Set(['ICE', 'IC', 'EC', 'ECE', 'TGV', 'RJ', 'RJX', 'NJ']);

export function trainClass(trainId = '') {
  return String(trainId).trim().split(/[\s\d]/)[0].toUpperCase();
}

function baseMedian(cls) {
  if (cls === 'ICE') return 8;
  if (LONG_DISTANCE.has(cls)) return 5;
  if (cls === 'S') return 2;
  return 3; // RE, RB, IRE, IR, BRB, ag, ALX, M, MEX, FEX ...
}

function hourFactor(iso) {
  const h = Number(new Intl.DateTimeFormat('en-GB', { hour: 'numeric', hour12: false, timeZone: 'Europe/Berlin' }).format(new Date(iso)));
  if (h >= 6 && h < 10) return 0.9;
  if (h >= 15 && h < 20) return 1.3;
  if (h >= 22 || h < 5) return 0.8;
  return 1.0;
}

/** Geometric pmf with its median exactly at `median`. */
export function geometric(median, size = 240) {
  const q = 0.5 ** (1 / (median + 1));
  const probs = new Array(size);
  for (let k = 0; k < size; k++) probs[k] = (1 - q) * q ** k;
  return probs;
}

/**
 * Real delay distributions have a fat tail: most runs are a few minutes late,
 * a minority hit a disruption and run 20-60 min late. Mix a routine geometric
 * with a disruption geometric so transfers under ~15 min carry visible risk.
 */
export function fatTailed(median, size = 240, disruptionShare = 0.18) {
  const routine = geometric(median, size);
  const disrupted = geometric(median * 4 + 12, size);
  return routine.map((p, k) => (1 - disruptionShare) * p + disruptionShare * disrupted[k]);
}

export function describeLeg(leg) {
  const cls = trainClass(leg.trainId);
  const hours = Math.max(0.25, minutesBetween(leg.plannedDeparture, leg.plannedArrival) / 60);
  const factor = hourFactor(leg.plannedDeparture) * (1 + 0.15 * hours);
  const median = Math.max(1, Math.round(baseMedian(cls) * factor));
  const pCancel = LONG_DISTANCE.has(cls) ? 0.02 : 0.03;
  return { cls, hours, median, pCancel };
}

export function createMockBackend({ size = 240 } = {}) {
  return {
    modelId: MODEL_ID,
    async forecast(journey) {
      return {
        modelId: MODEL_ID,
        confidence: 'low',
        legs: journey.legs.map((leg) => {
          const { cls, hours, median, pCancel } = describeLeg(leg);
          const hh = new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Berlin' }).format(new Date(leg.plannedDeparture));
          return {
            trainId: leg.trainId,
            arrival: forecast(fatTailed(median, size), pCancel),
            departure: forecast(fatTailed(Math.max(1, Math.round(median * 0.4)), size, 0.08), pCancel),
            reasoning: `Prior for ${cls} departing ${hh} on a ${hours.toFixed(1)} h leg: typical +${median} min; no live data behind this number.`,
            sources: ['mock: train-class × hour × duration prior v1'],
          };
        }),
      };
    },
  };
}
