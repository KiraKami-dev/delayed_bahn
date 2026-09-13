# Current frontend — single-screen journey companion (13 September 2026)

Akshat authorized a full frontend redo around the supplied transcript:
comfortable journeys, per-train delay estimates chained across connections,
and actionable recommendations. The main flow is one mobile viewport with
three bottom views: My journey, What next?, Why? Content is paged instead
of appended down a long page. The live Germany globe remains mounted.

Higgsfield generated public/travel-assets.png: a train, umbrella with luggage,
and disruption signal. CSS presents the three panels as decorative assets.
The previous rail-globe.png is retained but not displayed.

Implemented:
- One continuously mounted MapLibre globe; Germany outlined with local Natural
  Earth geometry. Gentle idle orbit stays around Germany and stops on map
  interaction or reduced-motion/pause preference.
- From/To or DB paste entry overlays the map. Search results, train legs,
  alternative legs, recovery scenarios and evidence text are paged. The fixed
  application has no document scroll; the sheet retains overflow access for
  enlarged text, keyboards and unusually long errors. DB Share auto-parses.
- Timetable lookup requests polylines. Solid lines follow supplied geometry;
  dashed lines explicitly represent station links when geometry is missing.
- Shared journeys get optional geometry lookup only on an exact match of
  every train, endpoint and scheduled departure/arrival. Prediction is not
  blocked by this enrichment. No backend or generated shared-type edits.
- Three.js miniatures follow supplied route geometry in the map projection.
  Their position/speed/size is illustrative, not live train tracking. Delay
  towers represent per-leg expected delay, capped visually at 30 minutes.
- My journey shows per-train delay, whole-journey connection risk, scheduled
  times and the remaining transfer buffer. A direct train shows arrival delay
  rather than a misleading zero connection-failure percentage.
- What next? offers the recommended action, leave-home preparation time,
  alternative scenarios and missed/cancelled-connection recovery. Synthetic
  alternatives remain labelled unverified.
- Why? contains paged source/reasoning text, a pending-validation statement
  for the placeholder model comparison, and optional level-3 cause evidence.
  Cause patterns never claim confirmed causality for a specific train.

Current verification: TypeScript/Vite production build and source checks.
Focused Node checks for geometry parsing, malformed coordinates, and exact
journey matching passed in the preceding map implementation. No Playwright/browser verification for this pass, per Akshat.
Earlier browser-check results describe earlier layouts only.

Limits: the live public timetable endpoint returned HTTP 503 in the prior
pass; actual geometry/route lookup still depends on that provider being
available and supplying polylines. Example fixtures lack track geometry and
remain dashed without 3D train positions. Tiles require connectivity unless
previously cached. The model remains a labelled prior/mock where returned
by the backend. Arrival-deadline/accessibility input, verified alternative
availability, held-out calibration and the unfrozen event contract still
need the previously identified product/data work.

Sources:
- https://v6.db.transport.rest/api.html (journeys: polylines parameter)
- https://maplibre.org/maplibre-gl-js/docs/examples/add-a-3d-model-to-globe-using-threejs/
- https://github.com/nvkelso/natural-earth-vector/blob/master/geojson/ne_110m_admin_0_countries.geojson
  (Natural Earth public-domain outline, Germany extracted into germany.geojson)
- Supplied team transcript and maintained event decisions/demo/contract.
  Entire graph is unavailable and checkpoint search needs login; historical
  intent is based on those supplied records, not an unread checkpoint.
