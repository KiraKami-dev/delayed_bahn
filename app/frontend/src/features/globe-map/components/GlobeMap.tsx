import * as maplibregl from "maplibre-gl"
import { useEffect, useRef, useState } from "react"
import { useStore } from "@/lib/store"
import { riskColour } from "@/lib/geo"
import { motionOff } from "@/lib/motion"
import { clearRoute, drawRoute, recolourRoute } from "../hooks/useRouteLayers"
import { fitJourney, flyToLeg, flyToStation, goHome, HOME, startIdleSpin } from "../camera"

// Two keyless basemaps. Default: Esri dark grey raster (renders everywhere, cheap).
// ?tiles=vector switches to OpenFreeMap's dark vector style (streets + labels).
// The service worker caches whatever tiles it sees (vite.config.ts).
const ESRI = "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas"
const RASTER_STYLE: maplibregl.StyleSpecification = {
  version: 8,
  sources: {
    base: {
      type: "raster",
      tiles: [`${ESRI}/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}`],
      tileSize: 256,
      maxzoom: 16,
      attribution: "Esri, HERE, Garmin, © OpenStreetMap contributors",
    },
    labels: {
      type: "raster",
      tiles: [`${ESRI}/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}`],
      tileSize: 256,
      maxzoom: 16,
    },
  },
  layers: [
    { id: "bg", type: "background", paint: { "background-color": "#07070c" } },
    { id: "base", type: "raster", source: "base", paint: { "raster-opacity": 0.92, "raster-fade-duration": 200 } },
    { id: "labels", type: "raster", source: "labels", minzoom: 5, paint: { "raster-opacity": 0.85, "raster-fade-duration": 200 } },
  ],
}
const VECTOR_STYLE = "https://tiles.openfreemap.org/styles/dark"

function pickStyle(): maplibregl.StyleSpecification | string {
  try {
    return new URLSearchParams(location.search).get("tiles") === "vector" ? VECTOR_STYLE : RASTER_STYLE
  } catch {
    return RASTER_STYLE
  }
}

export function GlobeMap() {
  const ref = useRef<HTMLDivElement>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)
  const [map, setMap] = useState<maplibregl.Map | null>(null)
  const s = useStore()

  const [failed, setFailed] = useState<string | null>(null)

  // Create the map once. WebGL can be missing (old device, headless run):
  // the app must keep working without the globe.
  useEffect(() => {
    if (!ref.current) return
    let m: maplibregl.Map
    try {
      m = new maplibregl.Map({
        container: ref.current,
        style: pickStyle(),
        center: HOME.center,
        zoom: HOME.zoom,
        attributionControl: { compact: true },
        dragRotate: false,
        pitchWithRotate: false,
        fadeDuration: 200,
      })
    } catch (e) {
      setFailed((e as Error).message || "WebGL unavailable")
      return
    }
    m.touchZoomRotate.disableRotation()
    m.on("error", (e) => console.warn("[map]", e.error?.message ?? e))
    m.on("load", () => {
      try {
        m.setProjection({ type: "globe" })
      } catch (e) {
        console.warn("[map] globe projection unavailable", e)
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


  const journey = s.journey
  const prediction = s.prediction
  const legColours = prediction
    ? prediction.legs.map((l, i) => {
        const last = i === prediction.legs.length - 1
        const p = last ? Math.min(1, l.expectedDelayMinutes.value / 30) : l.missProbability.value
        return riskColour(p)
      })
    : undefined

  // Idle: home view with a slow spin.
  useEffect(() => {
    if (!map) return
    if (journey) return
    clearRoute(map, "main")
    clearRoute(map, "alt")
    goHome(map)
    const stop = startIdleSpin(map)
    return stop
  }, [map, journey])

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
  }, [map, journey?.id])

  // Forecast arrived: recolour, then fly to the breaking transfer.
  useEffect(() => {
    if (!map || !journey || !prediction || !legColours) return
    recolourRoute(map, "main", journey, legColours)
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
  }, [map, prediction?.journeyId, s.tab === "forecast"])

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
      drawRoute(map, "alt", s.recommendation.alternative, { dashed: true, labels: false, colours: journey.legs.map(() => "#6ee7b7") })
      fitJourney(map, [journey, s.recommendation.alternative])
    } else if (s.overlay === "reroute" && s.reroute) {
      const opt = s.reroute.options[s.rerouteChoice] ?? s.reroute.options[0]
      if (opt) {
        drawRoute(map, "alt", opt.journey, { dashed: true, labels: false, colours: opt.journey.legs.map(() => "#6ee7b7"), width: 5 })
        fitJourney(map, [opt.journey], { maxZoom: 11 })
      }
    } else if (s.tab === "advice" || s.tab === "plan") {
      fitJourney(map, [journey])
    }
  }, [map, journey, s.overlay, s.recommendation?.alternative, s.reroute, s.rerouteChoice, s.tab])

  // Causes tab → dive into the selected station; Evidence → pull back to the globe.
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
    }
    window.addEventListener("resize", onResize)
    return () => window.removeEventListener("resize", onResize)
  }, [map, journey, s.overlay])

  if (failed)
    return (
      <div className="map-root flex items-center justify-center bg-[radial-gradient(circle_at_30%_30%,#15152a,#07070c_60%)] text-center text-sm text-muted-foreground">
        <p className="max-w-xs px-6">The 3D map needs WebGL, which this browser does not provide. Everything else works.</p>
      </div>
    )
  return <div ref={ref} className="map-root" aria-label="Map of the journey" />
}
