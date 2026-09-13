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

### Service-specific train visuals

Akshat requested train visuals driven by the selected service and restricted to its supplied track. The frontend now retains timetable category/product/operator metadata, classifies ICE, IC/EC, RE, RB and S-Bahn, and uses matching category silhouettes in the map and journey card. Unrecognized or conflicting categories use a neutral train. These are illustrative silhouettes, not verified fleet models, liveries, carriage counts or live positions.

Each miniature carriage is sampled independently by distance along the provider polyline. Missing, invalid or zero-length geometry produces no miniature; malformed provider segments are rejected rather than bridged. The freestanding delay towers were removed; returned delay information remains in route labels and the journey panel.

Validation: production build and 17 non-browser map/service/track smoke checks pass. No Playwright or visual browser validation was run; mobile rendering and route animation still need Akshat's review. Vite emitted its existing large-map-chunk warning and the concurrent smoke runners reported an occupied HMR socket while all assertions passed.

### Germany framing update

The initial and reset camera now center on Germany at country scale, with a minimum zoom of 4 and no idle drift. Selecting a journey still fits its track geometry around the mobile panel. Production build and 24 non-browser camera/route/service checks passed; visual verification remains with Akshat.

### Globe exploration, slow trains and route-entry recovery

Germany remains the initial view; minimum zoom is now zero and wheel/pinch/button zoom can reveal the full globe. Trains are enlarged (capped to their supplied track length), run on a 90-second illustrative travel timeline, pause briefly for matching model delays, and carry service/estimated-delay labels. A matching journey ID and train ID are required for a delay label. Visibility changes resume animation without jumping through elapsed background time. Orientation follows the direction of travel.

Only returned warning notices produce obstacle assets: works barriers, weather clouds or warning signals. Locations and replay are explicitly illustrative. Notices are readable in the journey card; no obstacle is inferred from station-level historical causes. Existing fixtures have no service notices, so they show delay visuals without fabricated obstacles.

Find my route now accepts exact station names/aliases, Enter selects a suggestion, and pointer handling keeps suggestions selectable. Provider errors remain truthful, endpoints are retained, and recovery offers Copy stations, Open DB and Paste DB journey. A live public request returned HTTP 503 during this pass; provider availability remains unresolved. Invalid arrival timestamps are excluded. No replacement schedules are invented.

Validation: 27 non-browser camera, service, route, delay-timeline and timetable-failure checks pass. Production build passes with the existing map-chunk warning. Browser/visual verification remains with Akshat; no Playwright was run. API reference: https://v6.db.transport.rest/api.html.

### Browser “Failed to fetch” diagnosis

The live provider response inspected with an Origin header returned HTTP 503 and no Access-Control-Allow-Origin header (13 September 2026). This is consistent with the browser reporting an unreadable network response instead of exposing the HTTP status. Route search now translates fetch rejection into a timetable-unavailable message, preserves the original diagnostic cause, and retains cancellation behavior. It does not claim the provider is repaired. Production build and all 15 focused route/service checks pass, including rejected-fetch and aborted-request regression cases. Browser CORS behavior reference: https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API/Using_Fetch#making_cross-origin_requests.
