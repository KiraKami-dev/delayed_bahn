# Feature: recommendation

`POST /api/recommend` `{ journey, prediction, doorToStationMin?, acceptableRisk? }`
-> `Recommendation` (contract) plus additive `leaveHomeBy`, `chosenDeparture`, `riskAfter`.
Rules: plan-fail below the accepted risk (default 15%) -> `good`; else search +5..+30 min at the weakest transfer -> `add-buffer`; else `take-alternative` from `fixtures/alternatives.json` or a synthesised earlier departure. Advice is written like a weather forecast.

`POST /api/reroute` `{ journey, missedLegIndex }` -> next connections from the station where the change broke (`fixtures/reroute.json`, else the remaining legs shifted +10/+20/+30 min), each scored with the prediction chain, best first. Serves demo shot 0:45 "recommendation" and the "I missed my connection" flow.
