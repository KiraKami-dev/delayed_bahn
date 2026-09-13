import { after, before, test } from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { createServer } from 'vite'
import { featureFilter, validateStyleMin } from '@maplibre/maplibre-gl-style-spec'

let server, camera, journey, basemap, geo, geometry, createEarthBasemap, applyBasemapMode
before(async () => {
  server = await createServer({ root: fileURLToPath(new URL('.', import.meta.url)), server: { middlewareMode: true }, appType: 'custom' })
  camera = await server.ssrLoadModule('/src/features/globe-map/camera.ts')
  const basemaps = await server.ssrLoadModule('/src/features/globe-map/basemap.ts')
  basemap = basemaps.detailedBasemap
  createEarthBasemap = basemaps.createEarthBasemap
  applyBasemapMode = basemaps.applyBasemapMode
  geo = await server.ssrLoadModule('/src/lib/geo.ts')
  geometry = await server.ssrLoadModule('/src/lib/route-geometry.ts')
  journey = JSON.parse(await readFile(new URL('./public/seed/journey.json', import.meta.url), 'utf8'))
})
after(async () => { await server?.close() })

function mapFixture(t, width, height, rect, hidden = false) {
  const originals = Object.fromEntries(['window', 'document', 'location'].map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)]))
  const sheet = { hidden, getBoundingClientRect: () => rect }
  globalThis.window = { innerWidth: width, innerHeight: height }
  globalThis.document = { querySelector: () => ({ querySelector: () => sheet }), documentElement: { dataset: { motion: '0' } } }
  globalThis.location = { search: '?motion=0' }
  t.after(() => {
    for (const [key, descriptor] of Object.entries(originals)) {
      if (descriptor) Object.defineProperty(globalThis, key, descriptor)
      else delete globalThis[key]
    }
  })
  let padding = { top: 0, bottom: 0, left: 0, right: 0 }
  const fits = []
  const flights = []
  const mapHeight = height - (height < 520 && width > height ? 48 : width >= 768 ? 66 : 58)
  return {
    fits,
    flights,
    setPadding(next) { padding = { ...next }; return this },
    getPadding() { return padding },
    flyTo(options) { flights.push(options); if (options.padding) padding = { ...options.padding }; return this },
    fitBounds(bounds, options) {
      const requested = options.padding
      const availableWidth = width - padding.left - padding.right - requested.left - requested.right
      const availableHeight = mapHeight - padding.top - padding.bottom - requested.top - requested.bottom
      assert.ok(availableWidth > 0 && availableHeight > 0, `MapLibre cannot fit: available area ${availableWidth} × ${availableHeight}`)
      assert.deepEqual(padding, { top: 0, bottom: 0, left: 0, right: 0 }, 'Old camera padding must not be counted twice')
      fits.push({ bounds, options })
      return this
    },
  }
}

for (const [width, height, rect] of [
  [375, 844, { top: 364, right: 365 }],
  [320, 568, { top: 112, right: 310 }],
  [844, 390, { top: 54, right: 398 }],
  [1440, 900, { top: 382, right: 418 }],
]) {
  test(`example trip fits after the padded globe at ${width}x${height}`, t => {
    const map = mapFixture(t, width, height, rect)
    camera.goHome(map)
    assert.deepEqual(map.flights[0].center, [10.5, 51], 'The initial view is centered on Germany')
    assert.ok(map.flights[0].zoom >= 4, 'Keep country-level detail instead of showing the whole globe')
    assert.ok(camera.HOME.zoom >= 4, 'The first map paint must also start at country scale')
    camera.fitJourney(map, [journey], { duration: 0 })
    assert.equal(map.fits[0].options.pitch, 0) // flat while motion is off
    assert.equal(map.fits[0].options.duration, 0)
    assert.equal(map.fits[0].options.padding.bottom, camera.panelPadding().bottom)
    camera.flyToStation(map, journey.legs[0].to)
    camera.flyToLeg(map, journey.legs[1])
    camera.fitJourney(map, [journey])
    assert.equal(map.fits.length, 3)
    assert.equal(map.fits[1].options.pitch, 0) // flat while motion is off
  })
}

test('map-only view keeps its framing when the sheet is hidden', t => {
  const map = mapFixture(t, 375, 844, { top: 364, right: 365 }, true)
  camera.goHome(map)
  camera.fitJourney(map, [journey])
  assert.equal(map.fits[0].options.padding.bottom, 81)
})

function matches(id, properties, type = 2) {
  const index = basemap.layers.findIndex(layer => layer.id === id)
  return featureFilter(basemap.layers[index].filter, `layers[${index}].filter`).filter({ zoom: 14 }, { type, properties })
}

test('detailed basemap is valid, uses vector geography, and distinguishes water from land', () => {
  assert.deepEqual(validateStyleMin(basemap).map(error => error.message), [])
  assert.equal(basemap.sources.openmaptiles.type, 'vector')
  assert.equal(basemap.sources.openmaptiles.url, 'https://tiles.openfreemap.org/planet')
  const water = basemap.layers.find(layer => layer.id === 'water')
  assert.equal(water['source-layer'], 'water')
  assert.equal(water.paint['fill-color'], '#a4cee5')
  assert.notEqual(water.paint['fill-color'], basemap.layers[0].paint['background-color'])
})

test('country and state borders use real administrative features and separate disputed borders', () => {
  assert.equal(basemap.layers.find(layer => layer.id === 'country-borders')['source-layer'], 'boundary')
  assert.equal(matches('country-borders', { admin_level: 2, disputed: 0, maritime: 0 }), true)
  assert.equal(matches('country-borders', { admin_level: 4 }), false)
  assert.equal(matches('country-borders', { admin_level: 2, disputed: 1 }), false)
  assert.equal(matches('country-borders', { admin_level: 2, maritime: 1 }), false)
  assert.equal(matches('state-borders', { admin_level: 4, disputed: 0, maritime: 0 }), true)
  assert.equal(matches('disputed-borders', { admin_level: 2, disputed: 1, maritime: 0 }), true)
})

test('rail layers select mapped tracks, not roads, and distinguish underground transit', () => {
  assert.equal(basemap.layers.find(layer => layer.id === 'rail-tracks')['source-layer'], 'transportation')
  assert.equal(matches('rail-tracks', { class: 'rail' }), true)
  assert.equal(matches('rail-tracks', { class: 'primary' }), false)
  assert.equal(matches('rail-tracks', { class: 'rail', brunnel: 'tunnel' }), false)
  assert.equal(matches('rail-tunnels', { class: 'rail', brunnel: 'tunnel' }), true)
  assert.equal(matches('local-transit', { class: 'transit', subclass: 'tram' }), true)
})

test('station labels select real rail stops rather than arbitrary points of interest', () => {
  assert.equal(basemap.layers.find(layer => layer.id === 'station-names')['source-layer'], 'poi')
  assert.equal(matches('station-names', { class: 'railway', subclass: 'station', name: 'Berlin Hauptbahnhof' }, 1), true)
  assert.equal(matches('station-names', { class: 'railway', subclass: 'halt' }, 1), true)
  assert.equal(matches('station-names', { class: 'restaurant' }, 1), false)
})

test('provider route geometry remains intact and the camera includes bends beyond the endpoints', t => {
  const map = mapFixture(t, 375, 844, { top: 364, right: 365 })
  const points = [[11.08, 49.44], [10.7, 49.1], [11.2, 48.7], [11.56, 48.14]]
  const routeGeometry = geometry.parseRouteGeometry({ type: 'Feature', geometry: { type: 'LineString', coordinates: points } })
  const leg = { ...journey.legs[0], routeGeometry }
  assert.deepEqual(geo.legLine(leg), points)
  camera.goHome(map)
  camera.flyToLeg(map, leg)
  assert.ok(map.fits[0].bounds[0][0] < 10.7)
  assert.ok(map.fits[0].bounds[1][0] > 11.56)
  assert.equal(geometry.routeMatches(leg, { ...leg, trainId: 'RB16' }), true)
  assert.equal(geometry.routeMatches(leg, { ...leg, plannedDeparture: '2026-09-13T05:00:00+02:00' }), false)
})

test('missing track geometry is not invented for the example trip', () => {
  assert.equal(geometry.parseRouteGeometry({ type: 'LineString', coordinates: [] }), undefined)
  assert.equal(geometry.parseRouteGeometry({ type: 'LineString', coordinates: [[11, 49]] }), undefined)
  const leg = journey.legs[0]
  assert.equal(leg.routeGeometry, undefined)
  assert.deepEqual(geo.legLine(leg), [[leg.from.lon, leg.from.lat], [leg.to.lon, leg.to.lat]])
})

test('Earth mode uses valid satellite imagery and atmosphere rather than painted land or water', () => {
  for (const mode of ['earth', 'map']) assert.deepEqual(validateStyleMin(createEarthBasemap(mode)).map(error => error.message), [])
  const earth = createEarthBasemap()
  assert.equal(earth.projection.type, 'globe')
  assert.ok(earth.sky['atmosphere-blend'])
  assert.equal(earth.sources['earth-imagery'].type, 'raster')
  assert.match(earth.sources['earth-imagery'].tiles[0], /World_Imagery\/MapServer\/tile\/\{z\}\/\{y\}\/\{x\}/)
  assert.match(earth.sources['earth-imagery'].attribution, /Esri/)
  for (const layer of earth.layers.filter(layer => layer.type === 'fill')) assert.equal(layer.layout.visibility, 'none')
  assert.equal(earth.layers.find(layer => layer.id === 'rail-tracks')['source-layer'], 'transportation')
  assert.equal(earth.layers.find(layer => layer.id === 'country-borders')['source-layer'], 'boundary')
})

test('Earth and map views switch without replacing journey layers or resetting the camera', () => {
  const initial = createEarthBasemap()
  const layers = new Map(initial.layers.map(layer => [layer.id, structuredClone(layer)]))
  const journeyLayer = { id: 'route-main-0-line', type: 'line', paint: { 'line-color': '#916019' } }
  layers.set(journeyLayer.id, journeyLayer)
  let sky
  const map = {
    getLayer: id => layers.get(id),
    setLayoutProperty(id, key, value) { const layer = layers.get(id); layer.layout = { ...layer.layout, [key]: value } },
    setPaintProperty(id, key, value) { const layer = layers.get(id); layer.paint = { ...layer.paint, [key]: value } },
    setSky(value) { sky = value },
    setStyle() { assert.fail('Appearance changes must not replace the map style') },
    flyTo() { assert.fail('Appearance changes must not move the camera') },
  }
  applyBasemapMode(map, 'map')
  assert.equal(layers.get('earth-imagery').layout.visibility, 'none')
  assert.equal(layers.get('water').layout.visibility, 'visible')
  assert.equal(layers.get('water').paint['fill-color'], '#a4cee5')
  assert.equal(sky['atmosphere-blend'], 0)
  applyBasemapMode(map, 'earth')
  assert.equal(layers.get('earth-imagery').layout.visibility, 'visible')
  assert.equal(layers.get('water').layout.visibility, 'none')
  assert.equal(layers.get('country-names').paint['text-color'], '#f1f6e9')
  assert.equal(layers.get(journeyLayer.id), journeyLayer)
  assert.equal(layers.size, initial.layers.length + 1)
})
