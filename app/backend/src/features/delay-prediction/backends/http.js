// Forward a Journey to the Python model server (PREDICT_URL). Expected reply:
// { modelId?, confidence?, legs: [{ trainId, arrival: { probs, pCancel }, departure?, reasoning?, sources? }] }
// Any failure is thrown; the service falls back to the mock and says so.
export function createHttpBackend({ url, fetchImpl = fetch, timeoutMs = 8000 } = {}) {
  if (!url) throw new Error('PREDICT_URL is required for the http backend');
  return {
    modelId: 'remote',
    async forecast(journey) {
      const res = await fetchImpl(url, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(journey),
        signal: AbortSignal.timeout(timeoutMs),
      });
      if (!res.ok) throw new Error(`model server replied ${res.status}`);
      const data = await res.json();
      if (!Array.isArray(data?.legs) || data.legs.length !== journey.legs.length) throw new Error('model server reply has no per-leg forecasts');
      for (const l of data.legs) if (!Array.isArray(l?.arrival?.probs)) throw new Error('model server leg is missing arrival.probs');
      return {
        modelId: data.modelId || 'OpenTSLM db-trip-delay (unversioned)',
        confidence: data.confidence || 'medium',
        legs: data.legs.map((l, i) => ({
          trainId: l.trainId || journey.legs[i].trainId,
          arrival: { probs: l.arrival.probs, pCancel: l.arrival.pCancel ?? 0 },
          departure: l.departure?.probs ? { probs: l.departure.probs, pCancel: l.departure.pCancel ?? 0 } : undefined,
          reasoning: l.reasoning || 'Fine-tuned model forecast.',
          sources: l.sources || [data.modelId || 'model server'],
        })),
      };
    },
  };
}
