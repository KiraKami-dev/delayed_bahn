// Station name -> { evaNumber, name, lat, lon }. Local table first, then the
// DB Timetables station lookup when credentials exist, else the bare name.
import { readFileSync } from 'node:fs';

export const DB_TIMETABLES_BASE = 'https://apis.deutschebahn.com/db-api-marketplace/apis/timetables/v1';

export function normaliseName(s = '') {
  return String(s)
    .toLowerCase()
    .replace(/ä/g, 'ae').replace(/ö/g, 'oe').replace(/ü/g, 'ue').replace(/ß/g, 'ss')
    .normalize('NFD').replace(/[̀-ͯ]/g, '')
    .replace(/hauptbahnhof/g, 'hbf')
    .replace(/\bmain station\b/g, 'hbf')
    .replace(/\bcentral station\b/g, 'hbf')
    .replace(/[^a-z0-9]+/g, ' ')
    .trim();
}

function loadTable() {
  return JSON.parse(readFileSync(new URL('./fixtures/stations.json', import.meta.url), 'utf8'));
}

export function createStationResolver({ env = process.env, stations, fetchImpl = fetch, timeoutMs = 4000 } = {}) {
  const table = stations ?? loadTable();
  const byEva = new Map();
  const byName = new Map();
  for (const s of table) {
    byEva.set(String(s.evaNumber), s);
    byName.set(normaliseName(s.name), s);
    for (const a of s.aliases || []) byName.set(normaliseName(a), s);
  }
  const cache = new Map();
  const pick = (s) => ({ evaNumber: String(s.evaNumber), name: s.name, lat: s.lat, lon: s.lon });

  function local(name) {
    const n = normaliseName(name);
    if (!n) return null;
    if (byName.has(n)) return pick(byName.get(n));
    // second pass: drop a trailing hbf/hb and parenthesised region
    const loose = n.replace(/\s*\(.*?\)\s*/g, ' ').replace(/\s+(hbf|hb)$/, '').trim();
    for (const [key, s] of byName) {
      const k = key.replace(/\s*\(.*?\)\s*/g, ' ').replace(/\s+(hbf|hb)$/, '').trim();
      if (k === loose) return pick(s);
    }
    return null;
  }

  async function remote(name) {
    if (!env.DB_CLIENT_ID || !env.DB_API_KEY) return null;
    if (cache.has(name)) return cache.get(name);
    try {
      const res = await fetchImpl(`${DB_TIMETABLES_BASE}/station/${encodeURIComponent(name)}`, {
        headers: { 'DB-Client-Id': env.DB_CLIENT_ID, 'DB-Api-Key': env.DB_API_KEY, Accept: 'application/xml' },
        signal: AbortSignal.timeout(timeoutMs),
      });
      if (!res.ok) { cache.set(name, null); return null; }
      const xml = await res.text();
      const m = /<station\b[^>]*\bname="([^"]*)"[^>]*\beva="(\d+)"/.exec(xml) || /<station\b[^>]*\beva="(\d+)"[^>]*\bname="([^"]*)"/.exec(xml);
      let hit = null;
      if (m) {
        const named = m[0].indexOf('name=') < m[0].indexOf('eva=');
        hit = { evaNumber: named ? m[2] : m[1], name: named ? m[1] : m[2] };
        const known = byEva.get(hit.evaNumber);
        if (known) hit = pick(known);
      }
      cache.set(name, hit);
      return hit;
    } catch {
      cache.set(name, null);
      return null;
    }
  }

  return {
    byEva: (eva) => (byEva.has(String(eva)) ? pick(byEva.get(String(eva))) : null),
    resolveLocal: local,
    async resolve(name) {
      const clean = String(name || '').trim();
      return local(clean) || (await remote(clean)) || { evaNumber: '', name: clean };
    },
    table,
  };
}
