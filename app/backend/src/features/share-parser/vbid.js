// Best-effort resolver for share texts that only carry a bahn.de link with
// ?vbid=. Uses the unofficial bahn.de web endpoint (may be bot-blocked), so it
// is behind BAHN_VBID_RESOLVER=1 and never the primary path.
export const VBID_ENDPOINT = 'https://www.bahn.de/web/api/angebote/verbindung/';

export function createVbidResolver({ env = process.env, fetchImpl = fetch, timeoutMs = 5000 } = {}) {
  const enabled = env.BAHN_VBID_RESOLVER === '1';
  return {
    enabled,
    async resolve(vbid) {
      if (!enabled) return null;
      const res = await fetchImpl(VBID_ENDPOINT + encodeURIComponent(vbid), {
        headers: { Accept: 'application/json', 'User-Agent': 'Mozilla/5.0 error404.ai' },
        signal: AbortSignal.timeout(timeoutMs),
      });
      if (!res.ok) throw new Error(`bahn.de replied ${res.status}`);
      const data = await res.json();
      const conn = data?.verbindungen?.[0] ?? data?.verbindung ?? data;
      const sections = conn?.verbindungsAbschnitte;
      if (!Array.isArray(sections)) throw new Error('no verbindungsAbschnitte in reply');
      const legs = sections
        .filter((s) => (s.verkehrsmittel?.typ || '').toUpperCase() !== 'WALK' && (s.verkehrsmittel?.typ || '').toUpperCase() !== 'TRANSFER')
        .map((s) => ({
          trainId: (s.verkehrsmittel?.name || s.verkehrsmittel?.mittelText || 'unknown').replace(/\s+/g, ' ').trim(),
          from: { evaNumber: String(s.abfahrtsOrtExtId || ''), name: s.abfahrtsOrt || '' },
          to: { evaNumber: String(s.ankunftsOrtExtId || ''), name: s.ankunftsOrt || '' },
          plannedDeparture: s.abfahrtsZeitpunkt,
          plannedArrival: s.ankunftsZeitpunkt,
        }));
      if (!legs.length) throw new Error('reply has no train legs');
      return legs;
    },
  };
}
