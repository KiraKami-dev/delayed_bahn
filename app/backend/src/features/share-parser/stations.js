// Station name -> { evaNumber, name, lat, lon }. Local table first, then the
// DB Timetables station lookup when credentials exist, else the bare name.
// Timetables has no coordinates, so remote hits get them by EVA from RIS::Stations,
// or from OpenStreetMap when the DB app has no RIS::Stations subscription.
import { readFileSync } from 'node:fs';

export const DB_TIMETABLES_BASE = 'https://apis.deutschebahn.com/db-api-marketplace/apis/timetables/v1';
export const RIS_STATIONS_BASE = 'https://apis.deutschebahn.com/db-api-marketplace/apis/ris-stations/v1';
export const OVERPASS_URL = 'https://overpass-api.de/api/interpreter';

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
  const coordinateCache = new Map(); // successes only: a dropped connection must not hide a station for good
  let risSubscribed = true;
  const pick = (s) => ({ evaNumber: String(s.evaNumber), name: s.name, lat: s.lat, lon: s.lon });
  const position = (lat, lon) => (Number.isFinite(lat) && Number.isFinite(lon) ? { lat, lon } : null);

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

  async function risCoordinates(eva) {
    if (!risSubscribed) return null;
    const res = await fetchImpl(`${RIS_STATIONS_BASE}/stop-places/by-key?keyType=EVA&key=${eva}`, {
      headers: { 'DB-Client-Id': env.DB_CLIENT_ID, 'DB-Api-Key': env.DB_API_KEY, Accept: 'application/vnd.de.db.ris+json' },
      signal: AbortSignal.timeout(timeoutMs),
    });
    if (res.status === 401 || res.status === 403) { risSubscribed = false; return null; }
    if (!res.ok) return null;
    const p = (await res.json()).stopPlaces?.[0]?.position;
    return p ? position(p.latitude, p.longitude) : null;
  }

  async function osmCoordinates(eva) {
    // OpenStreetMap tags German stations with their EVA number as uic_ref.
    const query = `[out:json][timeout:10];nwr["uic_ref"="${eva}"];out center 1;`;
    const res = await fetchImpl(`${OVERPASS_URL}?data=${encodeURIComponent(query)}`, {
      headers: { Accept: 'application/json', 'User-Agent': 'delayedBahn-backend' }, // Overpass answers 406 without one
      signal: AbortSignal.timeout(timeoutMs),
    });
    if (!res.ok) return null;
    const el = (await res.json()).elements?.[0];
    return el ? position(el.lat ?? el.center?.lat, el.lon ?? el.center?.lon) : null;
  }

  async function coordinates(eva) {
    if (!/^\d{6,8}$/.test(eva)) return null;
    if (coordinateCache.has(eva)) return coordinateCache.get(eva);
    for (const source of [risCoordinates, osmCoordinates]) {
      const hit = await source(eva).catch(() => null);
      if (hit) { coordinateCache.set(eva, hit); return hit; }
    }
    return null;
  }

  return {
    byEva: (eva) => (byEva.has(String(eva)) ? pick(byEva.get(String(eva))) : null),
    resolveLocal: local,
    async resolve(name) {
      const clean = String(name || '').trim();
      const found = local(clean) || (await remote(clean));
      if (!found) return { evaNumber: '', name: clean };
      if (found.lat != null && found.lon != null) return found;
      const at = await coordinates(found.evaNumber);
      return at ? { ...found, ...at } : found;
    },
    table,
  };
}
