// journey-search: GET /api/journeys/search?from=EVA&to=EVA&departure=ISO
// Direct trains between two stations from the official DB Timetables API
// (plan/{eva}/{yymmdd}/{hh}). Needs DB_CLIENT_ID + DB_API_KEY. The plan feed
// lists each train's planned path, so a train is a candidate when the
// destination sits on its onward path; the arrival time comes from the
// destination's own plan for that train number. Connections with changes are
// not computed here (the frontend falls back to transport.rest for those).
import { createStationResolver, normaliseName, DB_TIMETABLES_BASE } from '../../share-parser/stations.js';

const fail = (status, message, details) => Object.assign(new Error(message), { status, details });
const BERLIN = 'Europe/Berlin';
const parts = new Intl.DateTimeFormat('en-GB', { timeZone: BERLIN, hourCycle: 'h23', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });

/** Berlin wall-clock fields for an instant. */
export function berlinFields(date) {
  const p = Object.fromEntries(parts.formatToParts(date).filter((x) => x.type !== 'literal').map((x) => [x.type, Number(x.value)]));
  return { y: p.year, m: p.month, d: p.day, h: p.hour, mi: p.minute };
}

/** DB "pt" (YYMMDDHHmm, Berlin local) -> ISO 8601 with the Berlin offset. */
export function ptToIso(pt) {
  const m = /^(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})$/.exec(String(pt || ''));
  if (!m) return null;
  const [y, mo, d, h, mi] = [2000 + Number(m[1]), Number(m[2]), Number(m[3]), Number(m[4]), Number(m[5])];
  const guess = Date.UTC(y, mo - 1, d, h, mi);
  for (const off of [120, 60]) {
    const instant = new Date(guess - off * 60000);
    const f = berlinFields(instant);
    if (f.y === y && f.m === mo && f.d === d && f.h === h && f.mi === mi) {
      const pad = (n) => String(n).padStart(2, '0');
      return `${y}-${pad(mo)}-${pad(d)}T${pad(h)}:${pad(mi)}:00+${pad(off / 60)}:00`;
    }
  }
  return null;
}

const decode = (s) => String(s).replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&apos;|&#39;/g, "'");
const attrs = (s) => Object.fromEntries([...s.matchAll(/([\w:-]+)="([^"]*)"/g)].map((m) => [m[1], decode(m[2])]));

/** Parse a DB Timetables plan document into stops: { category, number, line, arrival?, departure? }. */
export function parsePlan(xml) {
  const out = [];
  for (const block of String(xml).matchAll(/<s\b[^>]*>([\s\S]*?)<\/s>/g)) {
    const body = block[1];
    const tl = /<tl\b([^>]*)\/>/.exec(body);
    if (!tl) continue;
    const label = attrs(tl[1]);
    const event = (tag) => {
      const m = new RegExp(`<${tag}\\b([^>]*)\\/>`).exec(body);
      if (!m) return undefined;
      const a = attrs(m[1]);
      return { pt: a.pt, iso: ptToIso(a.pt), platform: a.pp, line: a.l, path: a.ppth ? a.ppth.split('|') : [] };
    };
    const arrival = event('ar');
    const departure = event('dp');
    out.push({ category: label.c || '', number: label.n || '', owner: label.o, line: departure?.line || arrival?.line, arrival, departure });
  }
  return out;
}

/** "RE7" + category RE -> "RE 7"; no line -> "ICE 507". */
export function trainLabel(stop) {
  const cat = stop.category;
  const line = stop.line || '';
  if (line) {
    const tail = line.toUpperCase().startsWith(cat.toUpperCase()) ? line.slice(cat.length).trim() : line;
    if (tail) return `${cat} ${tail}`;
  }
  return `${cat} ${stop.number}`.trim();
}

/** "München Hbf" matches "München Hbf (tief)" and "Berlin Hbf" matches "Berlin Hbf (tief)": DB names sub-stations by suffix. */
export const sameStation = (a, b) => {
  const x = normaliseName(a); const y = normaliseName(b);
  return Boolean(x && y) && (x === y || x.startsWith(`${y} `) || y.startsWith(`${x} `));
};

export function createJourneySearchService({ env = process.env, fetchImpl = fetch, stations, timeoutMs = 6000, now = () => new Date(), maxRequests = 30, maxMeta = 4, planTtlMs = 20 * 60000 } = {}) {
  const resolver = createStationResolver({ env, stations, fetchImpl });
  const enabled = Boolean(env.DB_CLIENT_ID && env.DB_API_KEY);
  const headers = { 'DB-Client-Id': env.DB_CLIENT_ID, 'DB-Api-Key': env.DB_API_KEY, Accept: 'application/xml' };
  const metaCache = new Map();
  const planCache = new Map(); // key -> { at, stops }; plan files are static timetable data, and DB allows 60 requests/minute

  /** DB's record for a station: its EVA, name and "meta" sub-stations (e.g. Berlin Hbf 8011160 + Berlin Hbf (tief) 8098160), which carry separate plans. */
  async function lookupStation(pattern) {
    const key = String(pattern);
    if (metaCache.has(key)) return metaCache.get(key);
    let hit = null;
    try {
      const res = await fetchImpl(`${DB_TIMETABLES_BASE}/station/${encodeURIComponent(key)}`, { headers, signal: AbortSignal.timeout(timeoutMs) });
      if (res.status === 429) throw fail(503, 'The DB timetable quota is used up for this minute; retry shortly');
      if (res.ok) {
        const m = /<station\b([^>]*)\/?>/.exec(await res.text());
        if (m) {
          const a = attrs(m[1]);
          if (a.eva) hit = { eva: a.eva, name: a.name || key, metas: (a.meta || '').split('|').filter((x) => /^\d{6,8}$/.test(x)).slice(0, maxMeta) };
        }
      }
    } catch (e) { if (e.status === 503) throw e; }
    metaCache.set(key, hit);
    return hit;
  }

  /** EVAs whose plans to scan for a station: our EVA, DB's EVA for the same name when it differs (local tables drift), and their metas. */
  async function stationEvas(eva, name) {
    const byEva = await lookupStation(eva);
    const byName = name && (!byEva || !sameStation(byEva.name, name)) ? await lookupStation(name) : null;
    const primary = byName || byEva || { eva: String(eva), metas: [] };
    const extra = byEva && byEva.eva !== primary.eva ? [byEva.eva, ...byEva.metas] : [];
    return [...new Set([primary.eva, ...primary.metas, ...extra])].slice(0, 1 + maxMeta);
  }

  async function fetchPlan(eva, budget) {
    const { y, m, d, h } = budget.at;
    const key = `${eva}/${String(y).slice(2)}${String(m).padStart(2, '0')}${String(d).padStart(2, '0')}/${String(h).padStart(2, '0')}`;
    const cached = planCache.get(key);
    if (cached && now().getTime() - cached.at < planTtlMs) return cached.stops;
    if (budget.used >= maxRequests) throw fail(504, 'The timetable search needed too many requests; try a nearer departure time');
    budget.used++;
    const res = await fetchImpl(`${DB_TIMETABLES_BASE}/plan/${key}`, { headers, signal: AbortSignal.timeout(timeoutMs) });
    if (res.status === 429) throw fail(503, 'The DB timetable quota is used up for this minute; retry shortly');
    if (res.status === 404 || res.status === 410) { planCache.set(key, { at: now().getTime(), stops: [] }); return []; }
    if (!res.ok) throw fail(502, `DB Timetables replied ${res.status} for ${key}`);
    const stops = parsePlan(await res.text());
    planCache.set(key, { at: now().getTime(), stops });
    return stops;
  }

  const hourAfter = (instantMs, n) => berlinFields(new Date(instantMs + n * 3600000));

  async function stationFor(eva, name) {
    const known = resolver.byEva(eva);
    if (known) return known;
    const remote = name ? await resolver.resolve(name) : null;
    return { evaNumber: String(eva), name: remote?.name || name || String(eva), ...(remote?.lat != null ? { lat: remote.lat, lon: remote.lon } : {}) };
  }

  return {
    enabled,
    resolver,
    /** Direct trains leaving `from` for `to` at or after `departure` (ISO or Date). */
    async search({ from, to, fromName, toName, departure, results = 5, hours = 2 }) {
      if (!enabled) throw fail(503, 'Timetable search is not configured: set DB_CLIENT_ID and DB_API_KEY on the backend');
      if (!/^\d{6,8}$/.test(String(from || '')) || !/^\d{6,8}$/.test(String(to || ''))) throw fail(400, 'from and to must be EVA station numbers');
      if (String(from) === String(to)) throw fail(400, 'from and to must differ');
      const start = departure ? new Date(departure) : now();
      if (Number.isNaN(start.getTime())) throw fail(400, 'departure must be an ISO 8601 timestamp');
      const [origin, destination, fromEvas, toEvas] = await Promise.all([stationFor(from, fromName), stationFor(to, toName), stationEvas(from, fromName), stationEvas(to, toName)]);
      const budget = { cache: new Map(), used: 0, at: berlinFields(start) };
      const plansAt = async (evas, instantMs, h) => { budget.at = hourAfter(instantMs, h); return (await Promise.all(evas.map((eva) => fetchPlan(eva, budget)))).flat(); };

      // A train sits in the plan file of its arrival hour and of its departure hour; keep one copy.
      const seen = new Set();
      const candidates = [];
      for (let h = 0; h < hours && candidates.length < results; h++) {
        for (const stop of await plansAt(fromEvas, start.getTime(), h)) {
          if (!stop.departure?.iso || Date.parse(stop.departure.iso) < start.getTime() - 60000) continue;
          if (!stop.departure.path.some((name) => sameStation(name, destination.name))) continue;
          const key = `${stop.category}|${stop.number}|${stop.departure.pt}`;
          if (seen.has(key)) continue;
          seen.add(key);
          candidates.push(stop);
        }
      }
      candidates.sort((a, b) => Date.parse(a.departure.iso) - Date.parse(b.departure.iso));
      const chosen = candidates.slice(0, results);

      const arrivals = new Map();
      if (chosen.length) {
        const first = Date.parse(chosen[0].departure.iso);
        for (let h = 0; h < 6 && arrivals.size < chosen.length; h++) {
          let stops;
          try { stops = await plansAt(toEvas, first, h); } catch (e) { if (e.status === 504) break; throw e; }
          for (const c of chosen) {
            if (arrivals.has(c)) continue;
            const hit = stops.find((s) => s.arrival?.iso && s.category === c.category && s.number === c.number && Date.parse(s.arrival.iso) > Date.parse(c.departure.iso) && s.arrival.path.some((name) => sameStation(name, origin.name)));
            if (hit) arrivals.set(c, hit);
          }
        }
      }

      const journeys = chosen.filter((c) => arrivals.has(c)).map((c) => {
        const arr = arrivals.get(c);
        const leg = {
          trainId: trainLabel(c),
          trainNumber: c.number,
          serviceCategory: c.category,
          from: { ...origin },
          to: { ...destination },
          plannedDeparture: c.departure.iso,
          plannedArrival: arr.arrival.iso,
        };
        if (c.departure.platform) leg.fromPlatform = c.departure.platform;
        if (arr.arrival.platform) leg.toPlatform = arr.arrival.platform;
        return { id: `search-${c.category}${c.number}-${c.departure.pt}`, source: 'manual', legs: [leg] };
      });
      return { journeys, source: 'db-timetables', direct: true, requests: budget.used, from: origin, to: destination, departure: start.toISOString() };
    },
  };
}

export function registerRoutes(router, ctx = {}) {
  const svc = ctx.service || createJourneySearchService(ctx);
  router.get('/api/journeys/search', async ({ query }) => svc.search({
    from: query.get('from'), to: query.get('to'), fromName: query.get('fromName') || undefined, toName: query.get('toName') || undefined,
    departure: query.get('departure') || undefined, results: Math.min(8, Math.max(1, Number(query.get('results')) || 5)),
  }));
  return svc;
}
