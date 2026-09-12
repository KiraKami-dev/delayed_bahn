// Grammar for the text the DB Navigator app shares. Built on this real sample:
//
//   Nürnberg Hbf → München Hbf
//   Sun 13.09.2026
//   RB16 (59143)
//   To München Hbf
//   From 04:34 Nürnberg Hbf, Platform 5 C-F
//   To 07:25 München Hbf, Platform 21
//   View journey: https://int.bahn.de/en/buchung/start?vbid=...
//
// A line tokenizer classifies each line, then a small state machine folds
// train / departure / arrival lines into legs and boundaries into connections.
import { createHash } from 'node:crypto';

const TRAIN_TYPES = 'ICE|ICS|IC|ECE|EC|IRE|IR|RE|RB|S|TGV|RJX|RJ|NJ|FEX|MEX|BRB|ALX|AG|M|EN|D|EST|THA|WB|FLX';
const TRAIN_RE = new RegExp(`^(${TRAIN_TYPES})\\s?(\\d{1,5})(?:\\s*\\((\\d{1,6})\\))?(?!\\d)`, 'i');
const STOP_TAGGED_RE = /^(from|to|ab|an|dep|arr|departure|arrival|abfahrt|ankunft)\.?:?\s*(\d{1,2}):(\d{2})(?:\s*uhr)?\s+(.+)$/i;
const STOP_LEADING_TIME_RE = /^(\d{1,2}):(\d{2})(?:\s*uhr)?\s+(?:(ab|an|dep|arr)\.?\s+)?(.+)$/i;
const STOP_TRAILING_TAG_RE = /^(.+?)\s+(ab|an|dep|arr)\.?\s+(\d{1,2}):(\d{2})$/i;
const PLATFORM_RE = /[,\s]*\b(platform|gleis|gl\.|pl\.|track|voie)\b.*$/i;
const DATE_DMY_RE = /(\d{1,2})\.(\d{1,2})\.(\d{4})/;
const DATE_ISO_RE = /(\d{4})-(\d{2})-(\d{2})/;
const URL_RE = /https?:\/\/\S+/i;
const TRANSFER_RE = /(umstieg|umsteigezeit|umsteigen|transfer(?:\s*time)?|change(?:\s*time)?)\D{0,20}?(\d{1,3})\s*min/i;
const BOUNDARY_RE = /^(verbindung|connection|option|alternative)\s*\d+\b|^-{3,}$|^={3,}$|^(dauer|duration|reisedauer|fahrtzeit|travel time)\b/i;
const HEADER_RE = /^(.+?)\s*(?:→|->|⟶|>)\s*(.+)$/;
const DIRECTION_RE = /^(to|nach|richtung|towards|direction)\s+(.+)$/i;

const DEP_TAGS = new Set(['from', 'ab', 'dep', 'departure', 'abfahrt']);

/** DB text pasted through a chat often loses its newlines; put them back before known line starts. */
export function splitLines(text) {
  const t = String(text)
    .replace(/\r\n?/g, '\n')
    .replace(/\s+(?=(?:From|To|Ab|An)\s+\d{1,2}:\d{2}\b)/g, '\n')
    .replace(/\s+(?=(?:View journey|Fahrt anzeigen|Show journey|Verbindung anzeigen)\s*:)/gi, '\n')
    .replace(/\s+(?=(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun|Mo|Di|Mi|Do|Fr|Sa|So)\.?,?\s*\d{1,2}\.\d{1,2}\.\d{4})/g, '\n')
    .replace(new RegExp(`\\s+(?=(?:${TRAIN_TYPES})\\s?\\d{1,5}\\s*\\(\\d+\\))`, 'g'), '\n')
    .replace(/(https?:\/\/\S+)/g, '$1\n');
  return t.split(/\n|\s\|\s/).map((l) => l.trim()).filter(Boolean);
}

function stopToken(tag, hh, mm, rest) {
  const station = rest.replace(PLATFORM_RE, '').replace(/[,\s]+$/, '').trim();
  const platform = (PLATFORM_RE.exec(rest)?.[0] || '').replace(/^[,\s]*/, '').trim() || undefined;
  return { type: 'STOP', tag, hh: Number(hh), mm: Number(mm), station, platform };
}

export function classify(line) {
  const url = URL_RE.exec(line);
  if (url) {
    const vbid = /[?&]vbid=([0-9a-fA-F-]{8,})/.exec(url[0])?.[1];
    return { type: 'URL', url: url[0], vbid };
  }
  const tr = TRANSFER_RE.exec(line);
  if (tr) return { type: 'TRANSFER', minutes: Number(tr[2]) };
  if (BOUNDARY_RE.test(line)) return { type: 'BOUNDARY' };
  const iso = DATE_ISO_RE.exec(line);
  const dmy = DATE_DMY_RE.exec(line);
  if (iso && !/\d{1,2}:\d{2}/.test(line)) return { type: 'DATE', y: +iso[1], m: +iso[2], d: +iso[3] };
  if (dmy && !/\d{1,2}:\d{2}/.test(line)) return { type: 'DATE', y: +dmy[3], m: +dmy[2], d: +dmy[1] };
  let m = STOP_TAGGED_RE.exec(line);
  if (m) return stopToken(DEP_TAGS.has(m[1].toLowerCase()) ? 'dep' : 'arr', m[2], m[3], m[4]);
  m = STOP_LEADING_TIME_RE.exec(line);
  if (m) return stopToken(m[3] ? (DEP_TAGS.has(m[3].toLowerCase()) ? 'dep' : 'arr') : null, m[1], m[2], m[4]);
  m = STOP_TRAILING_TAG_RE.exec(line);
  if (m) return stopToken(DEP_TAGS.has(m[2].toLowerCase()) ? 'dep' : 'arr', m[3], m[4], m[1]);
  m = TRAIN_RE.exec(line);
  if (m) return { type: 'TRAIN', trainId: `${m[1].toUpperCase()} ${m[2]}`, trainNumber: m[3] || undefined };
  m = DIRECTION_RE.exec(line);
  if (m) return { type: 'DIRECTION', station: m[2].trim() };
  m = HEADER_RE.exec(line);
  if (m && !/\d{1,2}:\d{2}/.test(line)) return { type: 'HEADER', origin: m[1].trim(), dest: m[2].trim() };
  return { type: 'NOISE', line };
}

export function tokenize(text) {
  return splitLines(text).map(classify);
}

/** Fold tokens into raw connections: { legs: [{trainId, trainNumber, from, dep, to, arr, transferMinutes?}], date, origin, dest, url, vbid, complete }. */
export function parseConnections(tokens) {
  const conns = [];
  let conn = fresh();
  let cur = null; // open leg awaiting its arrival
  let pendingTrain = null;

  function fresh() { return { legs: [], date: null, origin: null, dest: null, url: null, vbid: null, complete: true, touched: false }; }
  function closeLeg() {
    if (cur) { conn.complete = false; cur = null; }
  }
  function flush() {
    closeLeg();
    if (conn.touched) conns.push(conn);
    conn = fresh();
    pendingTrain = null;
  }

  for (const t of tokens) {
    if (t.type !== 'BOUNDARY' && t.type !== 'NOISE') conn.touched = true;
    switch (t.type) {
      case 'BOUNDARY': flush(); break;
      case 'DATE': conn.date = { y: t.y, m: t.m, d: t.d }; break;
      case 'URL': conn.url = t.url; if (t.vbid) conn.vbid = t.vbid; break;
      case 'HEADER': conn.origin = t.origin; conn.dest = t.dest; break;
      case 'TRAIN':
        if (cur) closeLeg();
        pendingTrain = { trainId: t.trainId, trainNumber: t.trainNumber };
        break;
      case 'DIRECTION': break; // "To München Hbf" without a time is the train's direction
      case 'TRANSFER':
        if (conn.legs.length) conn.legs.at(-1).transferMinutes = t.minutes;
        break;
      case 'STOP': {
        const isDep = t.tag === 'dep' || (t.tag === null && !cur);
        if (isDep) {
          if (cur) closeLeg();
          cur = { trainId: pendingTrain?.trainId ?? null, trainNumber: pendingTrain?.trainNumber, from: t.station, dep: { hh: t.hh, mm: t.mm }, fromPlatform: t.platform };
          pendingTrain = null;
        } else {
          if (!cur) { conn.complete = false; break; } // arrival with no open leg
          cur.to = t.station; cur.arr = { hh: t.hh, mm: t.mm }; cur.toPlatform = t.platform;
          if (!cur.trainId && pendingTrain) { cur.trainId = pendingTrain.trainId; cur.trainNumber = pendingTrain.trainNumber; pendingTrain = null; }
          conn.legs.push(cur);
          cur = null;
        }
        break;
      }
      default: break;
    }
  }
  flush();
  return conns;
}

export function isComplete(conn) {
  return conn.legs.length > 0 && conn.legs.every((l) => l.from && l.to && l.dep && l.arr);
}

export function pickFirstComplete(conns) {
  return conns.find((c) => c.complete && isComplete(c)) || conns.find(isComplete) || null;
}

// --- time helpers -----------------------------------------------------------

const OFFSET_FMT = new Intl.DateTimeFormat('en-US', { timeZone: 'Europe/Berlin', timeZoneName: 'longOffset' });

/** "+02:00" for the Europe/Berlin offset in force at the given UTC instant. */
export function berlinOffset(at) {
  const part = OFFSET_FMT.formatToParts(at).find((p) => p.type === 'timeZoneName')?.value || 'GMT+01:00';
  const m = /GMT([+-]\d{2}):?(\d{2})?/.exec(part);
  return m ? `${m[1]}:${m[2] || '00'}` : '+01:00';
}

export function berlinIso(date, hh, mm) {
  const pad = (n) => String(n).padStart(2, '0');
  const probe = new Date(Date.UTC(date.y, date.m - 1, date.d, 12));
  const offset = berlinOffset(probe);
  return `${date.y}-${pad(date.m)}-${pad(date.d)}T${pad(hh)}:${pad(mm)}:00${offset}`;
}

function addDays(date, n) {
  const d = new Date(Date.UTC(date.y, date.m - 1, date.d + n, 12));
  return { y: d.getUTCFullYear(), m: d.getUTCMonth() + 1, d: d.getUTCDate() };
}

export function todayInBerlin(now = new Date()) {
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Berlin', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(now);
  const get = (t) => Number(parts.find((p) => p.type === t).value);
  return { y: get('year'), m: get('month'), d: get('day') };
}

/** Raw connection -> legs with ISO times. Times roll to the next day when they go backwards. */
export function materialise(conn, { now = new Date() } = {}) {
  let date = conn.date || todayInBerlin(now);
  let lastMinutes = -1;
  const legs = conn.legs.map((l) => {
    const depMin = l.dep.hh * 60 + l.dep.mm;
    if (depMin < lastMinutes) date = addDays(date, 1);
    const plannedDeparture = berlinIso(date, l.dep.hh, l.dep.mm);
    const arrMin = l.arr.hh * 60 + l.arr.mm;
    if (arrMin < depMin) date = addDays(date, 1);
    const plannedArrival = berlinIso(date, l.arr.hh, l.arr.mm);
    lastMinutes = arrMin;
    return { trainId: l.trainId || 'unknown', trainNumber: l.trainNumber, from: l.from, to: l.to, plannedDeparture, plannedArrival, transferMinutes: l.transferMinutes, fromPlatform: l.fromPlatform, toPlatform: l.toPlatform };
  });
  for (let i = 0; i < legs.length - 1; i++) {
    if (typeof legs[i].transferMinutes !== 'number') {
      legs[i].transferMinutes = Math.round((Date.parse(legs[i + 1].plannedDeparture) - Date.parse(legs[i].plannedArrival)) / 60000);
    }
  }
  return legs;
}

export function journeyId(legs) {
  const key = legs.map((l) => `${l.trainId}|${l.plannedDeparture}|${l.from?.evaNumber || l.from?.name || l.from}`).join('#');
  return 'jrn_' + createHash('sha1').update(key).digest('hex').slice(0, 10);
}
