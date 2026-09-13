import { before, after, test } from 'node:test'
import assert from 'node:assert/strict'
import { createServer } from 'vite'
import { fileURLToPath } from 'node:url'
let server, service, track, geometry
before(async () => {
  server = await createServer({ root: fileURLToPath(new URL('.', import.meta.url)), server: { middlewareMode: true }, appType: 'custom' })
  service = await server.ssrLoadModule('/src/lib/train-service.ts')
  track = await server.ssrLoadModule('/src/lib/track-path.ts')
  geometry = await server.ssrLoadModule('/src/lib/route-geometry.ts')
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
