import { LocateFixed, Minus, Navigation, Plus, TrainFront } from "lucide-react"
import * as maplibregl from "maplibre-gl"
import mapWorkerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url"
import { useEffect, useRef, useState } from "react"
import { useStore } from "@/lib/store"
import { riskColour, riskMapColour } from "@/lib/geo"
import { DUR, motionOff, useReducedMotion } from "@/lib/motion"
import { createTrainLayer, type TrainLayer } from "../train-layer"
import { applyBasemapMode, createEarthBasemap, type BasemapMode } from "../basemap"
import { resolveJourneyGeometry } from "@/lib/journey-search"
import { validTrack } from "@/lib/track-path"
import { reuseMappedServiceGeometry } from "@/lib/osm-route"
import type { Journey } from "@/lib/contract"
import { clearRoute, drawRoute, recolourRoute } from "../hooks/useRouteLayers"
import { fitJourney, flyToLeg, flyToStation, goHome, HOME, panelPadding } from "../camera"

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
  // Chase camera: on for a fresh journey, off as soon as the traveller moves the map themselves.
  const [follow, setFollow] = useState(true)
  const trainLayer = useRef<TrainLayer | null>(null)
  const holdUntil = useRef(0)
  const hold = (ms: number) => { holdUntil.current = Math.max(holdUntil.current, performance.now() + ms) }

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
    if (!original || original.legs.every(l => validTrack(l.routeGeometry))) return
    const controller = new AbortController()
    let active = true
    const timeout = window.setTimeout(() => controller.abort(), 30000)
    void resolveJourneyGeometry(original, controller.signal).then(next => {
      if (active && !controller.signal.aborted) setResolved(next)
    }).catch(() => { /* Preserve the parsed journey and explicitly dashed fallback. */ }).finally(() => {
      window.clearTimeout(timeout)
    })
    return () => { active = false; controller.abort(); window.clearTimeout(timeout) }
  }, [s.journey])
  const followActive = follow && !still && Boolean(journey) && s.overlay === "none" && (s.tab === "plan" || s.tab === "forecast" || s.tab === "advice")

  // Any hands-on gesture ends the chase camera; the button brings it back.
  useEffect(() => {
    if (!map) return
    const stop = (e: { originalEvent?: unknown }) => { if (e.originalEvent) setFollow(false) }
    map.on("dragstart", stop); map.on("zoomstart", stop); map.on("rotatestart", stop); map.on("pitchstart", stop); map.on("wheel", stop)
    return () => { map.off("dragstart", stop); map.off("zoomstart", stop); map.off("rotatestart", stop); map.off("pitchstart", stop); map.off("wheel", stop) }
  }, [map])
  useEffect(() => { setFollow(true); hold(DUR.fly + 900) }, [s.journey?.id])

  // Chase camera: glide behind the active train, looking along the track.
  useEffect(() => {
    if (!map || !followActive) return
    let frame = 0, last = performance.now(), bearing: number | undefined
    const tick = (now: number) => {
      frame = requestAnimationFrame(tick)
      const dt = Math.min(100, now - last); last = now
      if (now < holdUntil.current || map.isMoving() && now < holdUntil.current) return
      const head = trainLayer.current?.head()
      if (!head) return
      const km = Math.max(1, head.trackLength / 1000)
      const zoom = Math.min(13.4, Math.max(11.2, 14.2 - .55 * Math.log2(km)))
      const targetBearing = head.heading * 180 / Math.PI
      const centre = map.getCenter()
      const far = Math.hypot(centre.lng - head.lon, centre.lat - head.lat) > .25 || Math.abs(map.getZoom() - zoom) > 2.5
      if (far) {
        bearing = targetBearing
        map.easeTo({ center: [head.lon, head.lat], zoom, pitch: 58, bearing: targetBearing, padding: panelPadding(), duration: 1400, essential: true })
        hold(1500)
        return
      }
      const k = 1 - Math.exp(-dt / 320)
      if (bearing == null) bearing = map.getBearing()
      let delta = ((targetBearing - bearing + 540) % 360) - 180
      bearing += delta * k
      const lng = centre.lng + (head.lon - centre.lng) * k
      const lat = centre.lat + (head.lat - centre.lat) * k
      map.jumpTo({ center: [lng, lat], zoom: map.getZoom() + (zoom - map.getZoom()) * k, pitch: map.getPitch() + (58 - map.getPitch()) * k, bearing, padding: panelPadding() })
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [map, followActive])
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
        colours: legColours,
        satellite: basemapMode === "earth",
        onStationClick: (i) => s.dispatch({ type: "selectLeg", index: i }),
      })
      if (!followActive) fitJourney(map, [journey])
      console.info("[route] drawn", journey.legs.length, "legs")
    } catch (e) {
      console.error("[route] draw failed", e)
    }
    return () => clearRoute(map, "main")
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map, journey, basemapMode])

  // 3D train models only once motion is switched on: by default the map shows the flat route.
  useEffect(() => {
    if (!map || !journey || still) return
    if (map.getLayer("journey-miniatures")) map.removeLayer("journey-miniatures")
    try { const layer = createTrainLayer(journey, prediction); map.addLayer(layer); trainLayer.current = layer } catch (error) { console.warn("3D trains unavailable", error) }
    map.triggerRepaint()
    return () => { trainLayer.current = null; if (map.getLayer("journey-miniatures")) map.removeLayer("journey-miniatures") }
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
      if (worst >= 0 && worstP >= 0.3) { flyToStation(map, journey.legs[worst].to, 10.5); hold(DUR.fly + 3500) }
      else if (!followActive) fitJourney(map, [journey])
    }, motionOff() ? 0 : 400)
    return () => window.clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map, journey, prediction, s.tab === "forecast"])

  // Card tap → fly to that leg.
  useEffect(() => {
    if (!map || !journey || s.selectedLeg == null) return
    const leg = journey.legs[s.selectedLeg]
    if (leg) { setFollow(false); flyToLeg(map, leg) }
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
    } else if ((s.tab === "advice" || s.tab === "plan") && !followActive) {
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
      if (journey && s.overlay === "none" && !followActive) fitJourney(map, [journey], { duration: 0 })
      else if (!journey) goHome(map)
    }
    const observer = new ResizeObserver(onResize)
    observer.observe(map.getContainer())
    window.addEventListener("rail-layout", onResize)
    return () => { observer.disconnect(); window.removeEventListener("rail-layout", onResize) }
  }, [map, journey, s.overlay, followActive])

  if (failed) return <div className="map-placeholder"><p>The interactive map isn’t supported by this browser. Your train details and forecast are still available below and beside the map.</p></div>
  return <>
    <div ref={ref} className="map-root" data-basemap={basemapMode} aria-label="Interactive map of the journey" />
    {map && <div className="map-controls" aria-label="Map controls">
      {map.getLayer("earth-imagery") && <button type="button" aria-label={basemapMode === "earth" ? "Switch to map view" : "Switch to satellite Earth"} title={basemapMode === "earth" ? "Switch to map view" : "Switch to satellite Earth"} onClick={() => { setImageryUnavailable(false); setBasemapMode(basemapMode === "earth" ? "map" : "earth") }}>{basemapMode === "earth" ? "Map" : "Earth"}</button>}
      {journey && !still && <button type="button" className="follow" aria-label={follow ? "Stop following the train" : "Follow the train"} title={follow ? "Stop following the train" : "Follow the train"} aria-pressed={follow} onClick={() => { setFollow(!follow); holdUntil.current = 0 }}><Navigation size={16} /></button>}
      <button type="button" aria-label="Zoom in" onClick={() => { setFollow(false); map.zoomIn({ duration: motionOff() ? 0 : 250 }) }}><Plus size={16} /></button>
      <button type="button" aria-label="Zoom out" onClick={() => { setFollow(false); map.zoomOut({ duration: motionOff() ? 0 : 250 }) }}><Minus size={16} /></button>
      <button type="button" aria-label="Fit whole journey" onClick={() => { setFollow(false); if (!journey) goHome(map); else { s.dispatch({ type: "selectLeg", index: null }); fitJourney(map, [journey]) } }}><LocateFixed size={16} /></button>
      <button type="button" aria-label="Show railway and station detail" title="Railway and station detail" onClick={() => { setFollow(false); if (journey) flyToStation(map, journey.legs[s.selectedLeg ?? 0].to, 13); else map.easeTo({ zoom: Math.max(8, map.getZoom()), duration: motionOff() ? 0 : 1200 }) }}><TrainFront size={16} /></button>
      <button type="button" aria-label={tilted ? "Switch to flat map" : "Switch to 3D map"} aria-pressed={tilted} onClick={() => { setFollow(false); map.easeTo({ pitch: tilted ? 0 : 50, bearing: tilted ? 0 : -15, duration: motionOff() ? 0 : 700 }) }}>{tilted ? "2D" : "3D"}</button>
    </div>}
    {(tileError || imageryUnavailable) && <div className="map-warning" role="status">{imageryUnavailable ? "Satellite imagery is unavailable. Showing the geographic map instead." : "Some map details are unavailable. Your trip summary is still available."}</div>}
  </>
}
