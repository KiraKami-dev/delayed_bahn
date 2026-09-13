import { before, after, test } from 'node:test'
import assert from 'node:assert/strict'
import { createServer } from 'vite'
import { fileURLToPath } from 'node:url'
import { readFile } from 'node:fs/promises'
let server, service, track, geometry, osm, search, cached, seed, story
before(async () => {
  server = await createServer({ root: fileURLToPath(new URL('.', import.meta.url)), server: { middlewareMode: true }, appType: 'custom' })
  story = await server.ssrLoadModule('/src/lib/train-story.ts')
  service = await server.ssrLoadModule('/src/lib/train-service.ts')
  track = await server.ssrLoadModule('/src/lib/track-path.ts')
  geometry = await server.ssrLoadModule('/src/lib/route-geometry.ts')
  osm = await server.ssrLoadModule('/src/lib/osm-route.ts')
  search = await server.ssrLoadModule('/src/lib/journey-search.ts')
  cached = JSON.parse(await readFile(new URL('./public/seed/mapped-routes.json', import.meta.url), 'utf8'))
  seed = JSON.parse(await readFile(new URL('./public/seed/journey.json', import.meta.url), 'utf8'))
})
after(async () => { await server?.close() })
test('returned service names select the category; unknown or contradictory data stays neutral', () => {
  for (const [trainId, kind] of [['ICE 75','ice'], ['RE1','re'], ['RB 14','rb'], ['S7','sbahn'], ['IC 2020','intercity'], ['TGV 3','unknown']]) assert.equal(service.trainVisual({trainId}).kind, kind)
  assert.equal(service.trainVisual({trainId:'123',serviceProduct:'suburban'}).kind,'sbahn')
  assert.equal(service.trainVisual({trainId:'ICE 75',serviceCategory:'RE'}).kind,'unknown')
})
test('invalid or zero-length geometry cannot receive train models', () => {
  for (const points of [undefined, [], [[13,52]], [[13,52],[13,52]], [[13,52],[NaN,53]], [[181,52],[13,53]]]) assert.equal(track.validTrack(points),false)
  assert.equal(track.validTrack([[13,52],[13.1,52.1]]),true)
})
test('carriage sampling follows distance along bends and preserves endpoints', () => {
  const points = [[13,52],[13.01,52],[13.01,52.04],[13.01,52.04]]
  const path = track.buildTrack(points)
  const corner = track.trackDistance(points[0],points[1])
  const first = track.sampleTrack(path,corner / 2)
  assert.equal(first.point[1],52)
  const second = track.sampleTrack(path,corner + 1000)
  assert.equal(second.point[0],13.01)
  assert.ok(second.point[1] > 52 && second.point[1] < 52.04)
  assert.deepEqual(track.sampleTrack(path,path.length).point,points.at(-1))
  assert.equal(track.sampleTrack(path,path.length).heading,0)
})

test('malformed provider points are rejected instead of joining across missing track', () => {
  const feature = coordinates => ({type:'Feature',geometry:{type:'Point',coordinates}})
  assert.equal(geometry.parseRouteGeometry({type:'FeatureCollection',features:[feature([13,52]), feature(null), feature([14,53])]}),undefined)
  assert.deepEqual(geometry.parseRouteGeometry({type:'LineString',coordinates:[[13,52,20],[14,53,30]]}),[[13,52],[14,53]])
})

const way = (points, role = '') => ({ type: 'way', role, geometry: points.map(([lon, lat]) => ({ lon, lat })) })
const stop = ([lon, lat]) => ({ type: 'node', role: 'stop', lon, lat })

test('OSM ways are joined in service order, including reversed ways, without bridging gaps', () => {
  const a = [11, 48], b = [11.01, 48], c = [11.01, 48.01], d = [11.02, 48.01]
  assert.deepEqual(osm.joinRouteWays([way([b, a]), way([b, c]), way([d, c])]), [a, b, c, d])
  assert.equal(osm.joinRouteWays([way([a, b]), way([[12, 49], [12.1, 49]])]), undefined)
  assert.equal(osm.joinRouteWays([way([a, b]), { type: 'way', role: '' }]), undefined)
  assert.deepEqual(osm.joinRouteWays([way([a, b]), way([[13, 52], [14, 53]], 'platform'), way([b, c])]), [a, b, c])
})

test('mapped services must match the train and station order before a route is trimmed', () => {
  const a = [11, 48], b = [11.01, 48], c = [11.01, 48.01], d = [11.02, 48.01]
  const relation = { id: 123, tags: { ref: 'S8', route: 'train', name: 'S8 mapped service' }, members: [stop(a), stop(b), stop(d), way([a, b]), way([b, c, d])] }
  const leg = { ...seed.legs[1], from: { name: 'Start', evaNumber: '1', lon: b[0], lat: b[1] }, to: { name: 'End', evaNumber: '2', lon: d[0], lat: d[1] } }
  const result = osm.mappedRouteForLeg(relation, leg, '2026-06-01T00:00:00Z')
  assert.deepEqual(result.coordinates, [b, c, d])
  assert.equal(result.relationId, 123)
  assert.equal(osm.mappedRouteForLeg(relation, { ...leg, trainId: 'S1' }, ''), undefined)
  assert.equal(osm.mappedRouteForLeg(relation, { ...leg, from: leg.to, to: leg.from }, ''), undefined)
  assert.equal(osm.mappedRouteForLeg(relation, { ...leg, from: { ...leg.from, lon: 14 } }, ''), undefined)
})

test('cached example routes have real bends, matching endpoints, and source attribution', () => {
  assert.equal(cached.source, 'OpenStreetMap')
  assert.equal(cached.license, 'ODbL-1.0')
  assert.equal(cached.routes.length, 2)
  for (const [i, leg] of seed.legs.entries()) {
    const route = cached.routes.find(route => osm.matchesMappedRoute(leg, route))
    assert.ok(route)
    assert.ok(route.coordinates.length > 500)
    const distance = track.buildTrack(route.coordinates).length
    const direct = track.trackDistance(route.coordinates[0], route.coordinates.at(-1))
    assert.ok(distance > direct * 1.15, 'The mapped route follows track bends, not a straight station chord')
    assert.ok(track.trackDistance(route.coordinates[0], [leg.from.lon, leg.from.lat]) < 800)
    assert.ok(track.trackDistance(route.coordinates.at(-1), [leg.to.lon, leg.to.lat]) < 800)
    assert.ok(distance > (i === 0 ? 190000 : 35000) && distance < (i === 0 ? 210000 : 45000))
  }
})

test('example routes load offline from the local asset without timetable or Overpass calls', async t => {
  const urls = []
  t.mock.method(globalThis, 'fetch', async url => {
    urls.push(String(url))
    assert.equal(String(url), '/seed/mapped-routes.json')
    return Response.json(cached)
  })
  const result = await search.resolveJourneyGeometry(seed, new AbortController().signal)
  assert.deepEqual(urls, ['/seed/mapped-routes.json'])
  assert.equal(result.id, seed.id)
  assert.equal(result.source, 'seed')
  for (const [i, leg] of result.legs.entries()) {
    assert.equal(leg.routeGeometrySource, 'osm')
    assert.ok(leg.routeGeometry.length > 500)
    assert.equal(leg.plannedDeparture, seed.legs[i].plannedDeparture)
    assert.equal(leg.trainId, seed.legs[i].trainId)
  }
  assert.equal(seed.legs[0].routeGeometry, undefined)
})

test('real journey geometry resolves per train and preserves returned service metadata', async t => {
  const queried = []
  const original = { ...seed, id: 'real-trip', source: 'db-share' }
  t.mock.method(globalThis, 'fetch', async input => {
    if (String(input) === '/seed/mapped-routes.json') return Response.json(cached)
    const url = new URL(input)
    assert.equal(url.hostname, 'v6.db.transport.rest')
    const leg = original.legs.find(leg => leg.from.evaNumber === url.searchParams.get('from'))
    queried.push(leg.trainId)
    assert.equal(url.searchParams.get('departure'), leg.plannedDeparture)
    assert.equal(url.searchParams.get('to'), leg.to.evaNumber)
    assert.equal(url.searchParams.get('polylines'), 'true')
    const shape = cached.routes.find(route => osm.matchesMappedRoute(leg, route)).coordinates
    return Response.json({ journeys: [{ legs: [{ line: { name: leg.trainId, mode: 'train', productName: 'RB', operator: { name: 'Example operator' } }, origin: { id: leg.from.evaNumber, name: leg.from.name }, destination: { id: leg.to.evaNumber, name: leg.to.name }, plannedDeparture: leg.plannedDeparture, plannedArrival: leg.plannedArrival, polyline: { type: 'LineString', coordinates: shape } }] }] })
  })
  const result = await search.resolveJourneyGeometry(original, new AbortController().signal)
  assert.deepEqual(queried.sort(), ['RB 16', 'S 8'])
  assert.ok(result.legs.every(leg => leg.routeGeometrySource === 'timetable'))
  assert.ok(result.legs.every(leg => leg.operatorName === 'Example operator'))
})

test('timetable failures use only a matching mapped service and retain the original train times', async t => {
  t.mock.method(globalThis, 'fetch', async url => String(url) === '/seed/mapped-routes.json' ? Response.json(cached) : new Response('', { status: 503 }))
  const result = await search.resolveJourneyGeometry({ ...seed, source: 'db-share' }, new AbortController().signal)
  assert.ok(result.legs.every(leg => leg.routeGeometrySource === 'osm'))
  assert.equal(result.legs[0].plannedArrival, seed.legs[0].plannedArrival)
  const unknown = { ...seed, legs: [{ ...seed.legs[0], trainId: 'Unknown train' }] }
  const unavailable = await search.resolveJourneyGeometry(unknown, new AbortController().signal)
  assert.equal(unavailable.legs[0].routeGeometry, undefined)
})

test('alternative timing scenarios reuse only the same mapped service, not another train or a dated timetable path', () => {
  const known = { ...seed, legs: seed.legs.map(leg => osm.applyMappedRoute(leg, cached.routes.find(route => osm.matchesMappedRoute(leg, route)))) }
  const alternative = { ...seed, id: 'scenario', legs: seed.legs.map(leg => ({ ...leg, plannedDeparture: '2026-09-13T03:34:00+02:00' })) }
  const mapped = osm.reuseMappedServiceGeometry(alternative, known)
  assert.equal(mapped.legs[0].routeGeometry, known.legs[0].routeGeometry)
  assert.equal(mapped.legs[0].plannedDeparture, alternative.legs[0].plannedDeparture)
  const differentTrain = { ...alternative, legs: [{ ...alternative.legs[0], trainId: 'ICE 100' }] }
  assert.equal(osm.reuseMappedServiceGeometry(differentTrain, known).legs[0].routeGeometry, undefined)
  const timetable = { ...known, legs: known.legs.map(leg => ({ ...leg, routeGeometrySource: 'timetable' })) }
  assert.equal(osm.reuseMappedServiceGeometry(alternative, timetable).legs[0].routeGeometry, undefined)
})

test('slow replay pauses only for the returned delay and uses a bounded visible train size', () => {
  assert.equal(story.storyProgress(45000, 0), .5)
  assert.equal(story.storyProgress(68000, 10), .7)
  assert.equal(story.storyProgress(70000, 10), .7)
  assert.ok(story.storyProgress(80000, 10) > .7)
  assert.ok(story.trainScale(9, 200000) >= 2500)
  assert.ok(story.trainScale(0, 1000) * 10.5 < 1000)
})
test('delays from another journey or another train cannot label this train', () => {
  const leg = seed.legs[0]
  const prediction = {journeyId:seed.id, legs:[{trainId:leg.trainId,expectedDelayMinutes:{value:12}}]}
  assert.equal(story.trainDelay(seed,leg,0,prediction),12)
  assert.equal(story.trainDelay(seed,leg,0,{...prediction,journeyId:'other'}),undefined)
  assert.equal(story.trainDelay(seed,{...leg,trainId:'other'},0,prediction),undefined)
})
test('lookup preserves service notices and rejects malformed arrival times', async t => {
  const originalFetch = globalThis.fetch
  t.after(() => { globalThis.fetch = originalFetch })
  const origin = {id:'8000261',name:'Nürnberg Hbf'}, destination = {id:'8000105',name:'Frankfurt Hbf'}
  const leg = {origin,destination,line:{name:'ICE 75',mode:'train'},plannedDeparture:'2026-09-13T08:00:00Z',plannedArrival:'2026-09-13T10:00:00Z',remarks:[{type:'warning',text:'Track works ahead'},{type:'hint',text:'Bicycle spaces'}]}
  globalThis.fetch = async () => ({ok:true,json:async () => ({journeys:[{legs:[leg]},{legs:[{...leg,plannedArrival:'invalid'}]}]})})
  const options = await search.searchJourneys({evaNumber:origin.id,name:origin.name},{evaNumber:destination.id,name:destination.name},new AbortController().signal)
  assert.equal(options.length,1)
  assert.equal(options[0].legs[0].disruptions.length,1)
  assert.equal(story.disruptionKind(options[0].legs[0].disruptions[0].text),'works')
  globalThis.fetch = async () => ({ok:false,status:503})
  await assert.rejects(search.searchJourneys({evaNumber:origin.id},{evaNumber:destination.id},new AbortController().signal), /HTTP 503/)
})
