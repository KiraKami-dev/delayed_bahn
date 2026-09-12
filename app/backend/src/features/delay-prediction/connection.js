// JS port of app/agents/src/features/db_delay/trip/connection.py.
// From per-train delay distributions to the chance that a change, and a
// journey, works out. Transfer times are applied here, after the model.
// Trains are treated as independent, which is optimistic when one disruption
// hits both; DB holding a connecting train is not modelled.

export const LATE_MINUTES = 6; // metrics.LATE_MINUTES: on time = delay < 6 min

/** A train's delay at one stop: probs[k] = P(delay = k min | runs), plus P(cancelled). */
export function forecast(probs, pCancel = 0) {
  return { probs: Array.from(probs, Number), pCancel };
}

export function normalised(f) {
  let total = 0;
  for (const p of f.probs) total += p;
  if (!(total > 0)) throw new Error('delay distribution has no mass');
  return Float64Array.from(f.probs, (p) => p / total);
}

/**
 * P(both trains run and arrival delay - departure delay <= plannedBuffer - minTransfer).
 * Python convolves a with reversed d; the sum over offsets <= slack equals
 * sum_i a[i] * P(D >= i - slack), which is what is computed here (no convolution).
 */
export function changeProbability(arriving, departing, plannedBuffer, minTransfer) {
  const a = normalised(arriving);
  const d = normalised(departing);
  const slack = Math.floor(plannedBuffer - minTransfer);
  const tail = new Float64Array(d.length + 1); // tail[k] = P(D >= k)
  for (let k = d.length - 1; k >= 0; k--) tail[k] = tail[k + 1] + d[k];
  let pMade = 0;
  for (let i = 0; i < a.length; i++) {
    if (a[i] === 0) continue;
    const k = i - slack;
    pMade += a[i] * (k <= 0 ? 1 : k >= d.length ? 0 : tail[k]);
  }
  return (1 - (arriving.pCancel ?? 0)) * (1 - (departing.pCancel ?? 0)) * pMade;
}

/**
 * Chain the changes of a journey into one success probability.
 * changes: [[arriving, departing, plannedBuffer, minTransfer], ...]
 */
export function journeyProbability(changes, finalArrival = null, arrivalSlack = null) {
  const changeProbabilities = changes.map(([arr, dep, buffer, minT]) => changeProbability(arr, dep, buffer, minT));
  let planSuccess = changeProbabilities.reduce((p, x) => p * x, 1);
  if (finalArrival && arrivalSlack !== null && arrivalSlack !== undefined) {
    const pmf = normalised(finalArrival);
    let onTime = 0;
    for (let k = 0; k <= Math.floor(arrivalSlack) && k < pmf.length; k++) onTime += pmf[k];
    planSuccess *= (1 - (finalArrival.pCancel ?? 0)) * onTime;
  }
  return { changeProbabilities, planSuccess, planFail: 1 - planSuccess };
}

/** A forecast certain of one delay, handy for tests and fixed timetables. */
export function point(minutes, size = 1000, pCancel = 0) {
  const probs = new Array(size).fill(0);
  probs[minutes] = 1;
  return { probs, pCancel };
}

/** Smallest k with CDF(k) >= q. */
export function quantile(f, q) {
  const p = normalised(f);
  let c = 0;
  for (let k = 0; k < p.length; k++) { c += p[k]; if (c >= q - 1e-12) return k; }
  return p.length - 1;
}

/** P(delay < LATE_MINUTES) * P(runs), as predict.py reports "chance of arriving on time". */
export function onTimeProbability(f) {
  const p = normalised(f);
  let c = 0;
  for (let k = 0; k < LATE_MINUTES && k < p.length; k++) c += p[k];
  return c * (1 - (f.pCancel ?? 0));
}

/** Coarse bins for the UI, including cancellation as its own bin. */
export const BINS = ['≤5', '5–15', '15–30', '>30', 'cancelled'];
export function binned(f) {
  const p = normalised(f);
  const runs = 1 - (f.pCancel ?? 0);
  const b = [0, 0, 0, 0];
  for (let k = 0; k < p.length; k++) {
    const i = k <= 5 ? 0 : k <= 15 ? 1 : k <= 30 ? 2 : 3;
    b[i] += p[k];
  }
  return { bins: BINS, probs: [...b.map((x) => x * runs), f.pCancel ?? 0] };
}

export function minutesBetween(isoA, isoB) {
  return (new Date(isoB).getTime() - new Date(isoA).getTime()) / 60000;
}
