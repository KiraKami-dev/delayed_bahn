import type { ExpressionSpecification, FilterSpecification, LayerSpecification, Map, StyleSpecification } from 'maplibre-gl'

const source = { source: 'openmaptiles' }
const label: ExpressionSpecification = ['coalesce', ['get', 'name:en'], ['get', 'name_en'], ['get', 'name']]
const localLabel: ExpressionSpecification = ['coalesce', ['get', 'name'], ['get', 'name:en'], ['get', 'name_en']]
const font = ['Noto Sans Regular']
const halo = { 'text-halo-color': '#fffff7', 'text-halo-width': 1.5, 'text-halo-blur': 0.3 }
const rail: FilterSpecification = ['all', ['==', ['get', 'class'], 'rail'], ['!=', ['get', 'brunnel'], 'tunnel']]
const transit: FilterSpecification = ['all', ['==', ['get', 'class'], 'transit'], ['!=', ['get', 'brunnel'], 'tunnel']]
const country: FilterSpecification = ['all', ['==', ['get', 'admin_level'], 2], ['!=', ['get', 'maritime'], 1], ['!=', ['get', 'disputed'], 1], ['!', ['has', 'claimed_by']]]
const station: FilterSpecification = ['all', ['==', ['get', 'class'], 'railway'], ['match', ['get', 'subclass'], ['station', 'halt', 'subway'], true, false]]

export const detailedBasemap: StyleSpecification = {
  version: 8,
  name: 'Rail travel · OpenStreetMap geography',
  sources: {
    openmaptiles: { type: 'vector', url: 'https://tiles.openfreemap.org/planet' },
  },
  glyphs: 'https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf',
  layers: [
    { id: 'background', type: 'background', paint: { 'background-color': '#edf1e4' } },
    { id: 'landcover', type: 'fill', ...source, 'source-layer': 'landcover', paint: {
      'fill-color': ['match', ['get', 'class'], 'wood', '#c6d9b5', 'grass', '#dce8c9', 'farmland', '#e8e7c8', 'sand', '#eee3c4', 'ice', '#f8fbfc', '#e1e8d2'],
      'fill-opacity': ['interpolate', ['linear'], ['zoom'], 3, 0.45, 8, 0.85],
    } },
    { id: 'landuse', type: 'fill', ...source, 'source-layer': 'landuse', minzoom: 8, paint: {
      'fill-color': ['match', ['get', 'class'], 'residential', '#ebece5', 'industrial', '#e2e1dd', 'commercial', '#e9e3db', 'railway', '#dce2e1', '#e3e9d8'],
      'fill-opacity': 0.7,
    } },
    { id: 'parks', type: 'fill', ...source, 'source-layer': 'park', minzoom: 7, paint: { 'fill-color': '#d0e2bb', 'fill-opacity': 0.65 } },
    { id: 'water', type: 'fill', ...source, 'source-layer': 'water', filter: ['!=', ['get', 'brunnel'], 'tunnel'], paint: { 'fill-color': '#a4cee5', 'fill-antialias': true } },
    { id: 'waterways', type: 'line', ...source, 'source-layer': 'waterway', minzoom: 7, filter: ['!=', ['get', 'brunnel'], 'tunnel'], paint: {
      'line-color': '#81b7d5', 'line-width': ['interpolate', ['linear'], ['zoom'], 7, 0.6, 12, 1.8, 16, 5],
    } },
    { id: 'buildings', type: 'fill', ...source, 'source-layer': 'building', minzoom: 13, paint: { 'fill-color': '#d8d7cc', 'fill-outline-color': '#c3c5b7' } },
    { id: 'roads-minor', type: 'line', ...source, 'source-layer': 'transportation', minzoom: 12, filter: ['match', ['get', 'class'], ['minor', 'service', 'track'], true, false], layout: { 'line-cap': 'round', 'line-join': 'round' }, paint: {
      'line-color': '#ffffff', 'line-width': ['interpolate', ['exponential', 1.4], ['zoom'], 12, 0.7, 16, 4, 20, 14],
    } },
    { id: 'footpaths', type: 'line', ...source, 'source-layer': 'transportation', minzoom: 14, filter: ['==', ['get', 'class'], 'path'], paint: {
      'line-color': '#a7b295', 'line-dasharray': [2, 2], 'line-width': ['interpolate', ['linear'], ['zoom'], 14, 0.7, 18, 1.6],
    } },
    { id: 'roads-major-casing', type: 'line', ...source, 'source-layer': 'transportation', minzoom: 5, filter: ['match', ['get', 'class'], ['motorway', 'trunk', 'primary', 'secondary', 'tertiary'], true, false], layout: { 'line-join': 'round' }, paint: {
      'line-color': '#d9d4bf', 'line-width': ['interpolate', ['exponential', 1.3], ['zoom'], 5, 0.25, 9, 1.4, 13, 4, 18, 16],
    } },
    { id: 'roads-major', type: 'line', ...source, 'source-layer': 'transportation', minzoom: 5, filter: ['match', ['get', 'class'], ['motorway', 'trunk', 'primary', 'secondary', 'tertiary'], true, false], layout: { 'line-join': 'round' }, paint: {
      'line-color': '#fffcef', 'line-width': ['interpolate', ['exponential', 1.3], ['zoom'], 5, 0.15, 9, 0.8, 13, 2.5, 18, 12],
    } },
    { id: 'rail-tunnels', type: 'line', ...source, 'source-layer': 'transportation', minzoom: 9, filter: ['all', ['match', ['get', 'class'], ['rail', 'transit'], true, false], ['==', ['get', 'brunnel'], 'tunnel']], paint: {
      'line-color': '#70828b', 'line-opacity': 0.65, 'line-dasharray': [2, 2], 'line-width': ['interpolate', ['linear'], ['zoom'], 9, 0.6, 13, 1.5, 17, 3],
    } },
    { id: 'rail-casing', type: 'line', ...source, 'source-layer': 'transportation', minzoom: 7, filter: rail, layout: { 'line-join': 'round' }, paint: {
      'line-color': '#fffffa', 'line-width': ['interpolate', ['linear'], ['zoom'], 7, 1.5, 10, 2.6, 14, 4.5, 18, 7],
    } },
    { id: 'rail-tracks', type: 'line', ...source, 'source-layer': 'transportation', minzoom: 7, filter: rail, layout: { 'line-join': 'round' }, paint: {
      'line-color': '#647b87', 'line-width': ['interpolate', ['linear'], ['zoom'], 7, 0.65, 10, 1.3, 14, 2.5, 18, 4.5],
    } },
    { id: 'rail-sleepers', type: 'line', ...source, 'source-layer': 'transportation', minzoom: 12, filter: rail, paint: {
      'line-color': '#526976', 'line-dasharray': [0.2, 3], 'line-width': ['interpolate', ['linear'], ['zoom'], 12, 3, 16, 6, 20, 9],
    } },
    { id: 'local-transit', type: 'line', ...source, 'source-layer': 'transportation', minzoom: 11, filter: transit, paint: {
      'line-color': '#78928f', 'line-width': ['interpolate', ['linear'], ['zoom'], 11, 0.65, 15, 1.8, 19, 3],
    } },
    { id: 'ferry-routes', type: 'line', ...source, 'source-layer': 'transportation', minzoom: 8, filter: ['==', ['get', 'class'], 'ferry'], paint: { 'line-color': '#518fab', 'line-width': 1, 'line-dasharray': [3, 3] } },
    { id: 'state-borders', type: 'line', ...source, 'source-layer': 'boundary', minzoom: 5, filter: ['all', ['>', ['get', 'admin_level'], 2], ['<=', ['get', 'admin_level'], 4], ['!=', ['get', 'maritime'], 1], ['!=', ['get', 'disputed'], 1], ['!', ['has', 'claimed_by']]], paint: {
      'line-color': '#83967b', 'line-opacity': 0.8, 'line-dasharray': [4, 2], 'line-width': ['interpolate', ['linear'], ['zoom'], 5, 0.6, 10, 1.2],
    } },
    { id: 'country-border-casing', type: 'line', ...source, 'source-layer': 'boundary', filter: country, layout: { 'line-join': 'round' }, paint: {
      'line-color': '#fffff5', 'line-opacity': 0.8, 'line-width': ['interpolate', ['linear'], ['zoom'], 2, 2.2, 7, 4.1, 13, 6],
    } },
    { id: 'country-borders', type: 'line', ...source, 'source-layer': 'boundary', filter: country, layout: { 'line-join': 'round' }, paint: {
      'line-color': '#64775d', 'line-width': ['interpolate', ['linear'], ['zoom'], 2, 0.7, 7, 1.7, 13, 2.8],
    } },
    { id: 'disputed-borders', type: 'line', ...source, 'source-layer': 'boundary', filter: ['all', ['==', ['get', 'disputed'], 1], ['!=', ['get', 'maritime'], 1]], paint: { 'line-color': '#8c8071', 'line-width': 1.3, 'line-dasharray': [2, 3] } },
    { id: 'road-names', type: 'symbol', ...source, 'source-layer': 'transportation_name', minzoom: 13, filter: ['match', ['get', 'class'], ['motorway', 'trunk', 'primary', 'secondary', 'tertiary', 'minor'], true, false], layout: {
      'symbol-placement': 'line', 'symbol-spacing': 300, 'text-field': localLabel, 'text-font': font, 'text-size': 11,
    }, paint: { ...halo, 'text-color': '#697367' } },
    { id: 'rail-names', type: 'symbol', ...source, 'source-layer': 'transportation_name', minzoom: 12, filter: ['match', ['get', 'class'], ['rail', 'transit'], true, false], layout: {
      'symbol-placement': 'line', 'symbol-spacing': 450, 'text-field': ['coalesce', ['get', 'name'], ['get', 'ref']], 'text-font': font, 'text-size': 10,
    }, paint: { ...halo, 'text-color': '#4f6b78' } },
    { id: 'water-names', type: 'symbol', ...source, 'source-layer': 'water_name', filter: ['==', ['geometry-type'], 'Point'], layout: {
      'text-field': label, 'text-font': ['Noto Sans Italic'], 'text-size': ['interpolate', ['linear'], ['zoom'], 2, 10, 10, 13], 'text-letter-spacing': 0.08,
    }, paint: { 'text-color': '#3c7899', 'text-halo-color': '#d4e8f3', 'text-halo-width': 1 } },
    { id: 'state-names', type: 'symbol', ...source, 'source-layer': 'place', minzoom: 5, maxzoom: 10, filter: ['==', ['get', 'class'], 'state'], layout: {
      'text-field': label, 'text-font': font, 'text-size': 11, 'text-letter-spacing': 0.12, 'text-transform': 'uppercase',
    }, paint: { ...halo, 'text-color': '#77846b' } },
    { id: 'town-names', type: 'symbol', ...source, 'source-layer': 'place', minzoom: 7, filter: ['match', ['get', 'class'], ['town', 'village', 'suburb'], true, false], layout: {
      'text-field': label, 'text-font': font, 'text-size': ['interpolate', ['linear'], ['zoom'], 7, 10, 14, 13], 'symbol-sort-key': ['coalesce', ['get', 'rank'], 10],
    }, paint: { ...halo, 'text-color': '#63735b' } },
    { id: 'city-names', type: 'symbol', ...source, 'source-layer': 'place', minzoom: 3, filter: ['==', ['get', 'class'], 'city'], layout: {
      'text-field': label, 'text-font': font, 'text-size': ['interpolate', ['linear'], ['zoom'], 3, 11, 7, 14, 12, 18], 'symbol-sort-key': ['coalesce', ['get', 'rank'], 10],
    }, paint: { ...halo, 'text-color': '#354d43' } },
    { id: 'country-names', type: 'symbol', ...source, 'source-layer': 'place', maxzoom: 8, filter: ['==', ['get', 'class'], 'country'], layout: {
      'text-field': label, 'text-font': ['Noto Sans Bold'], 'text-size': ['interpolate', ['linear'], ['zoom'], 2, 11, 6, 17], 'text-letter-spacing': 0.08, 'text-transform': 'uppercase',
    }, paint: { ...halo, 'text-color': '#435e46' } },
    { id: 'station-dots', type: 'circle', ...source, 'source-layer': 'poi', minzoom: 11, filter: station, paint: {
      'circle-radius': ['interpolate', ['linear'], ['zoom'], 11, 2, 16, 4], 'circle-color': '#ffffff', 'circle-stroke-color': '#416d7b', 'circle-stroke-width': 1.5,
    } },
    { id: 'station-names', type: 'symbol', ...source, 'source-layer': 'poi', minzoom: 12, filter: station, layout: {
      'text-field': localLabel, 'text-font': font, 'text-size': ['interpolate', ['linear'], ['zoom'], 12, 11, 16, 13], 'text-anchor': 'top', 'text-offset': [0, 0.7], 'text-max-width': 11,
    }, paint: { ...halo, 'text-color': '#345e6a' } },
  ],
}

export type BasemapMode = 'earth' | 'map'

const earthSky: NonNullable<StyleSpecification['sky']> = {
  'sky-color': '#071b2e',
  'horizon-color': '#a9d7ee',
  'fog-color': '#d3e6ed',
  'sky-horizon-blend': 0.55,
  'horizon-fog-blend': 0.35,
  'fog-ground-blend': 0.12,
  'atmosphere-blend': ['interpolate', ['linear'], ['zoom'], 0, 0.85, 4, 0.55, 7, 0],
}

function earthOverlay(layer: LayerSpecification): LayerSpecification {
  if (layer.type === 'background') return { ...layer, paint: { 'background-color': '#071b2e' } }
  if (layer.type === 'fill') return { ...layer, layout: { ...layer.layout, visibility: 'none' } }
  if (layer.type === 'symbol') return { ...layer, paint: { ...layer.paint, 'text-color': '#f1f6e9', 'text-halo-color': '#142c31', 'text-halo-width': 1.8, 'text-halo-blur': 0.5, 'text-opacity': ['interpolate', ['linear'], ['zoom'], 1.8, 0, 3.2, 1] } }
  if (layer.type !== 'line') return layer
  const border = layer.id.includes('border')
  const casing = layer.id.includes('casing')
  const track = layer.id.startsWith('rail') || layer.id === 'local-transit'
  const color = casing ? '#183332' : border ? '#e9efc7' : track ? '#c5dce4' : layer.id === 'waterways' ? '#83b7d0' : '#eee9d3'
  return { ...layer, paint: { ...layer.paint, 'line-color': color, 'line-opacity': border ? ['interpolate', ['linear'], ['zoom'], 1, 0.12, 4, 0.55, 7, 0.75] : track ? 0.9 : 0.4 } }
}

export function createEarthBasemap(mode: BasemapMode = 'earth'): StyleSpecification {
  const earth = mode === 'earth'
  const [background, ...overlays] = detailedBasemap.layers
  return {
    ...detailedBasemap,
    name: earth ? 'Earth · satellite imagery and rail geography' : detailedBasemap.name,
    projection: { type: 'globe' },
    sky: earth ? earthSky : { ...earthSky, 'sky-color': '#e4edf2', 'horizon-color': '#f7f8f2', 'fog-color': '#f7f8f2', 'atmosphere-blend': 0 },
    sources: {
      ...detailedBasemap.sources,
      'earth-imagery': {
        type: 'raster',
        tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'],
        tileSize: 256,
        maxzoom: 19,
        attribution: 'Imagery © Esri, Vantor, Earthstar Geographics and the GIS User Community',
      },
    },
    layers: [
      earth ? earthOverlay(background) : background,
      { id: 'earth-imagery', type: 'raster', source: 'earth-imagery', layout: { visibility: earth ? 'visible' : 'none' }, paint: { 'raster-opacity': 1, 'raster-saturation': 0.05, 'raster-contrast': 0.05, 'raster-fade-duration': 300 } },
      ...overlays.map(layer => earth ? earthOverlay(layer) : layer),
    ],
  }
}

export function applyBasemapMode(map: Map, mode: BasemapMode) {
  if (!map.getLayer('earth-imagery')) return
  const next = createEarthBasemap(mode)
  const previous = createEarthBasemap(mode === 'earth' ? 'map' : 'earth')
  next.layers.forEach((layer, index) => {
    if (!map.getLayer(layer.id)) return
    map.setLayoutProperty(layer.id, 'visibility', layer.layout?.visibility ?? 'visible')
    const paint = (layer.paint ?? {}) as Record<string, unknown>
    const oldPaint = (previous.layers[index].paint ?? {}) as Record<string, unknown>
    for (const key of new Set([...Object.keys(oldPaint), ...Object.keys(paint)])) map.setPaintProperty(layer.id, key as Parameters<Map['setPaintProperty']>[1], paint[key] as Parameters<Map['setPaintProperty']>[2])
  })
  map.setSky(next.sky!)
}

