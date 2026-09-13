import { LocateFixed, Minus, Plus, TrainFront } from "lucide-react"
import * as maplibregl from "maplibre-gl"
import mapWorkerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url"
import { useEffect, useRef, useState } from "react"
import { useStore } from "@/lib/store"
import { riskColour, riskMapColour } from "@/lib/geo"
import { motionOff, useReducedMotion } from "@/lib/motion"
import { createTrainLayer } from "../train-layer"
import { applyBasemapMode, createEarthBasemap, type BasemapMode } from "../basemap"
import { resolveJourneyGeometry } from "@/lib/journey-search"
import { validTrack } from "@/lib/track-path"
import { reuseMappedServiceGeometry } from "@/lib/osm-route"
import type { Journey } from "@/lib/contract"
import { clearRoute, drawRoute, recolourRoute } from "../hooks/useRouteLayers"
import { fitJourney, flyToLeg, flyToStation, goHome, HOME } from "../camera"

// Two keyless basemaps. Default: Esri dark grey raster (renders everywhere, cheap).
// ?tiles=vector switches to OpenFreeMap's dark vector style (streets + labels).
// The service worker caches whatever tiles it sees (vite.config.ts).
const ESRI = "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas"
const RASTER_STYLE: maplibregl.StyleSpecification = {
  version: 8,
  sources: {
    base: {
      type: "raster",
      tiles: [`${ESRI}/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}`],
      tileSize: 256,
      maxzoom: 16,
      attribution: "Esri, HERE, Garmin, © OpenStreetMap contributors",
    },
    labels: {
      type: "raster",
      tiles: [`${ESRI}/World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}`],
      tileSize: 256,
      maxzoom: 16,
    },
  },
  layers: [
    { id: "bg", type: "background", paint: { "background-color": "#edf1e7" } },
    { id: "base", type: "raster", source: "base", paint: { "raster-opacity": 0.92, "raster-fade-duration": 200 } },
    { id: "labels", type: "raster", source: "labels", minzoom: 5, paint: { "raster-opacity": 0.85, "raster-fade-duration": 200 } },
  ],
}
function initialBasemapMode(): BasemapMode {
  return ["vector", "raster"].includes(new URLSearchParams(location.search).get("tiles") ?? "") ? "map" : "earth"
}

function pickStyle(mode: BasemapMode): maplibregl.StyleSpecification {
  return new URLSearchParams(location.search).get("tiles") === "raster" ? RASTER_STYLE : createEarthBasemap(mode)
}

export function GlobeMap() {
  const ref = useRef<HTMLDivElement>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)
  const [map, setMap] = useState<maplibregl.Map | null>(null)
  const s = useStore()
  const still = useReducedMotion()
  const [resolved, setResolved] = useState<Journey | null>(null)
  const [geometryLoading, setGeometryLoading] = useState(false)
  const [geometryAttempt, setGeometryAttempt] = useState(0)

  const [failed, setFailed] = useState<string | null>(null)
  const [tileError, setTileError] = useState(false)
  const [tilted, setTilted] = useState(false)
  const [basemapMode, setBasemapMode] = useState<BasemapMode>(initialBasemapMode)
  const [imageryUnavailable, setImageryUnavailable] = useState(false)

  // Create the map once. WebGL can be missing (old device, headless run):
  // the app must keep working without the globe.
  useEffect(() => {
    if (!ref.current) return
    let m: maplibregl.Map
    try {
      maplibregl.setWorkerUrl(mapWorkerUrl)
      m = new maplibregl.Map({
        container: ref.current,
        style: pickStyle(basemapMode),
        center: HOME.center,
        zoom: HOME.zoom,
        minZoom: 0,
        attributionControl: { compact: true },
        dragRotate: true,
        pitchWithRotate: true,
        scrollZoom: true,
        cooperativeGestures: true,
        maxPitch: 65,
        fadeDuration: 200,
      })
    } catch (e) {
      setFailed((e as Error).message || "WebGL unavailable")
      return
    }
    m.touchZoomRotate.disableRotation()
    m.on("error", (event) => {
      if (("sourceId" in event && event.sourceId === "earth-imagery") || event.error.message.includes("World_Imagery")) {
        setImageryUnavailable(true)
        setBasemapMode("map")
      } else setTileError(true)
    })
    m.on("moveend", () => setTilted(m.getPitch() > 10))
    m.on("load", () => {
      try {
        m.setProjection({ type: "globe" })
      } catch (e) {
        console.warn("[map] globe projection unavailable", e)
      }
      if (!m.getSource("openmaptiles")) {
        m.addSource("germany-focus", { type: "geojson", data: "/germany.geojson", attribution: "Natural Earth" })
        m.addLayer({ id: "germany-fill", type: "fill", source: "germany-focus", maxzoom: 6, paint: { "fill-color": "#759f67", "fill-opacity": .08 } })
        m.addLayer({ id: "germany-border", type: "line", source: "germany-focus", maxzoom: 6, paint: { "line-color": "#547c47", "line-width": 1.5, "line-opacity": .7 } })
      }
      setMap(m)
    })
    mapRef.current = m
    return () => {
      m.remove()
      mapRef.current = null
      setMap(null)
    }
  }, [])

  useEffect(() => {
    if (map) applyBasemapMode(map, basemapMode)
  }, [map, basemapMode])

  const journey = resolved?.id === s.journey?.id ? resolved ?? s.journey : s.journey
  useEffect(() => {
    const original = s.journey
    setResolved(null)
    setGeometryLoading(false)
    if (!original || original.legs.every(l => validTrack(l.routeGeometry))) return
    const controller = new AbortController()
    let active = true
    setGeometryLoading(true)
    const timeout = window.setTimeout(() => controller.abort(), 30000)
    void resolveJourneyGeometry(original, controller.signal).then(next => {
      if (active && !controller.signal.aborted) setResolved(next)
    }).catch(() => { /* Preserve the parsed journey and explicitly dashed fallback. */ }).finally(() => {
      window.clearTimeout(timeout)
      if (active) setGeometryLoading(false)
    })
    return () => { active = false; controller.abort(); window.clearTimeout(timeout) }
  }, [s.journey, geometryAttempt])
  const prediction = s.prediction
  const legColours = prediction
    ? prediction.legs.map((l, i) => {
        const last = i === prediction.legs.length - 1
        const p = last ? Math.min(1, l.expectedDelayMinutes.value / 30) : l.missProbability.value
        return riskMapColour(p)
      })
    : undefined

  // Keep Germany in view until a journey is selected.
  useEffect(() => {
    if (!map) return
    if (journey) return
    clearRoute(map, "main")
    clearRoute(map, "alt")
    goHome(map)
  }, [map, journey, still])

  // Journey drawn and framed.
  useEffect(() => {
    if (!map || !journey) return
    try {
      drawRoute(map, "main", journey, {
        colours: undefined,
        onStationClick: (i) => s.dispatch({ type: "selectLeg", index: i }),
      })
      fitJourney(map, [journey])
      console.info("[route] drawn", journey.legs.length, "legs")
    } catch (e) {
      console.error("[route] draw failed", e)
    }
    return () => clearRoute(map, "main")
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map, journey])

  useEffect(() => {
    if (!map || !journey) return
    if (map.getLayer("journey-miniatures")) map.removeLayer("journey-miniatures")
    try { map.addLayer(createTrainLayer(journey, prediction)) } catch (error) { console.warn("3D trains unavailable", error) }
    map.triggerRepaint()
    return () => { if (map.getLayer("journey-miniatures")) map.removeLayer("journey-miniatures") }
  }, [map, journey, prediction, still])

  // Forecast arrived: recolour, then fly to the breaking transfer.
  useEffect(() => {
    if (!map || !journey || !prediction || !legColours) return
    recolourRoute(map, "main", journey, legColours)
    map.getContainer().querySelectorAll<HTMLButtonElement>(".station-marker").forEach(marker => {
      const index = journey.legs.findIndex(l => l.to.name === marker.getAttribute("aria-label"))
      if (index < 0) return
      let factor = marker.querySelector<HTMLElement>(".station-factor")
      if (!factor) { factor = document.createElement("span"); factor.className = "station-factor"; marker.append(factor) }
      const leg = prediction.legs[index]
      factor.textContent = `+${Math.round(leg.expectedDelayMinutes.value)} min${index < journey.legs.length - 1 ? ` · ${Math.round(leg.missProbability.value * 100)}% transfer risk` : ' arrival estimate'}`
    })
    if (s.tab !== "forecast") return
    let worst = -1
    let worstP = 0
    prediction.legs.forEach((l, i) => {
      if (i < prediction.legs.length - 1 && l.missProbability.value > worstP) {
        worstP = l.missProbability.value
        worst = i
      }
    })
    const t = window.setTimeout(() => {
      if (worst >= 0 && worstP >= 0.3) flyToStation(map, journey.legs[worst].to, 10.5)
      else fitJourney(map, [journey])
    }, motionOff() ? 0 : 400)
    return () => window.clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map, journey, prediction, s.tab === "forecast"])

  // Card tap → fly to that leg.
  useEffect(() => {
    if (!map || !journey || s.selectedLeg == null) return
    const leg = journey.legs[s.selectedLeg]
    if (leg) flyToLeg(map, leg)
  }, [map, journey, s.selectedLeg])

  // Alternative / re-route overlays.
  useEffect(() => {
    if (!map || !journey) return
    clearRoute(map, "alt")
    if (s.overlay === "alternative" && s.recommendation?.alternative) {
      const alternative = reuseMappedServiceGeometry(s.recommendation.alternative, journey)
      drawRoute(map, "alt", alternative, { dashed: true, labels: false, colours: alternative.legs.map(() => "#6ee7b7") })
      fitJourney(map, [journey, alternative])
    } else if (s.overlay === "reroute" && s.reroute) {
      const opt = s.reroute.options[s.rerouteChoice] ?? s.reroute.options[0]
      if (opt) {
        const reroute = reuseMappedServiceGeometry(opt.journey, journey)
        drawRoute(map, "alt", reroute, { dashed: true, labels: false, colours: reroute.legs.map(() => "#6ee7b7"), width: 5 })
        fitJourney(map, [reroute], { maxZoom: 11 })
      }
    } else if (s.tab === "advice" || s.tab === "plan") {
      fitJourney(map, [journey])
    }
  }, [map, journey, s.overlay, s.recommendation?.alternative, s.reroute, s.rerouteChoice, s.tab])

  // Causes tab → dive into the selected station; Evidence → pull back to the journey.
  useEffect(() => {
    if (!map || !journey) return
    if (s.tab === "causes") {
      const i = s.selectedLeg ?? 0
      const st = journey.legs[Math.min(i, journey.legs.length - 1)].to
      flyToStation(map, st, 12)
    } else if (s.tab === "evidence") {
      map.flyTo({ center: [10.5, 50], zoom: 3.2, pitch: 0, bearing: 0, duration: motionOff() ? 0 : 2000, essential: true })
    }
  }, [map, journey, s.tab, s.selectedLeg])

  // Keep the framing right when the viewport changes.
  useEffect(() => {
    if (!map) return
    const onResize = () => {
      map.resize()
      if (journey && s.overlay === "none") fitJourney(map, [journey], { duration: 0 })
      else if (!journey) goHome(map)
    }
    const observer = new ResizeObserver(onResize)
    observer.observe(map.getContainer())
    window.addEventListener("rail-layout", onResize)
    return () => { observer.disconnect(); window.removeEventListener("rail-layout", onResize) }
  }, [map, journey, s.overlay])

  if (failed) return <div className="map-placeholder"><p>The interactive map isn’t supported by this browser. Your train details and forecast are still available below and beside the map.</p></div>
  return <>
    <div ref={ref} className="map-root" data-basemap={basemapMode} aria-label="Interactive map of the journey" />
    {map && <div className="map-controls" aria-label="Map controls">
      {map.getLayer("earth-imagery") && <button type="button" aria-label={basemapMode === "earth" ? "Switch to map view" : "Switch to satellite Earth"} title={basemapMode === "earth" ? "Switch to map view" : "Switch to satellite Earth"} onClick={() => { setImageryUnavailable(false); setBasemapMode(basemapMode === "earth" ? "map" : "earth") }}>{basemapMode === "earth" ? "Map" : "Earth"}</button>}
      <button type="button" aria-label="Zoom in" onClick={() => map.zoomIn({ duration: motionOff() ? 0 : 250 })}><Plus size={16} /></button>
      <button type="button" aria-label="Zoom out" onClick={() => map.zoomOut({ duration: motionOff() ? 0 : 250 })}><Minus size={16} /></button>
      <button type="button" aria-label="Fit whole journey" onClick={() => { if (!journey) goHome(map); else { s.dispatch({ type: "selectLeg", index: null }); fitJourney(map, [journey]) } }}><LocateFixed size={16} /></button>
      <button type="button" aria-label="Show railway and station detail" title="Railway and station detail" onClick={() => { if (journey) flyToStation(map, journey.legs[s.selectedLeg ?? 0].to, 13); else map.easeTo({ zoom: Math.max(8, map.getZoom()), duration: motionOff() ? 0 : 1200 }) }}><TrainFront size={16} /></button>
      <button type="button" aria-label={tilted ? "Switch to flat map" : "Switch to 3D map"} aria-pressed={tilted} onClick={() => map.easeTo({ pitch: tilted ? 0 : 50, bearing: tilted ? 0 : -15, duration: motionOff() ? 0 : 700 })}>{tilted ? "2D" : "3D"}</button>
    </div>}
    <div className="geometry-note" aria-live="polite">{journey ? geometryLoading ? "Loading service track routes…" : journey.legs.every(l => validTrack(l.routeGeometry)) ? journey.legs.some(l => l.routeGeometrySource === "osm") ? "Mapped service tracks · not live diversions" : "Timetable route · illustrative trains, not live" : "Some track geometry is unavailable; dashed links are schematic" : basemapMode === "earth" ? "Satellite imagery · not live weather" : "OpenStreetMap borders · zoom in for railway tracks"}{journey && !geometryLoading && journey.legs.some(l => !validTrack(l.routeGeometry)) && <button type="button" onClick={() => setGeometryAttempt(attempt => attempt + 1)} style={{ pointerEvents: "auto" }} className="ml-2 min-h-8 underline">Retry tracks</button>}<span>{journey?.legs.some(l => l.routeGeometrySource === "osm") ? "Track paths: © OpenStreetMap contributors (ODbL). They describe the mapped service, not today's diversions. " : "Blue-gray lines: mapped rail network. "}{journey ? "Slow illustrative replay · not live positions. Delay labels are model estimates; obstacle locations are illustrative and require a service notice." : "Photographic land and oceans, with mapped borders and railway detail."}</span></div>
    {(tileError || imageryUnavailable) && <div className="map-warning" role="status">{imageryUnavailable ? "Satellite imagery is unavailable. Showing the geographic map instead." : "Some map details are unavailable. Your trip summary is still available."}</div>}
  </>
}
