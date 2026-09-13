# Source assessment

Generated 2026-09-13 05:29 UTC over window 2025-11-02..2026-08-31. 354 candidates from four registries (known list, HuggingFace, govdata CKAN, Zenodo); 18 passed every gate (7 probed live, 11 accepted on metadata only and not used), 336 rejected. Every verdict is a deterministic predicate; the reason is the first gate that failed.

## Accepted and probed live

| source | kind | licence | role | what the probe measured |
|---|---|---|---|---|
| `known:piebro/deutsche-bahn-data` | events | CC-BY-4.0 | primary series | {"n_columns": 18, "per_month": {"2025-10": {"rows": 1989180, "stations": 107}, "2025-11": {"rows": 13943561, "stations": 5293}, "2026-08": {"rows": 14270628, "stations": 5203}}, "has_actual_times": tr |
| `known:openholidays` | calendar | ODbL-1.0 | annotations | {"school_periods_BY": 7, "public_holidays_BY": 13} |
| `known:db-stations` | reference | ISC | join hub | {"stations": 5388} |
| `known:bright-sky` | weather | DL-DE-BY-2.0 | context channels | {"hourly_rows_one_week": 169} |
| `known:infrago-infrastruktur` | infrastructure | CC-BY-4.0 | context channels | {"size_mb": null} |
| `known:zensus-2022-grid` | reference | DL-DE-BY-2.0 | context channels | {"size_mb": null} |
| `hf:piebro/deutsche-bahn-data` | unknown | CC-BY-4.0 | primary series | {"n_columns": 18, "per_month": {"2025-10": {"rows": 1989180, "stations": 107}, "2025-11": {"rows": 13943561, "stations": 5293}, "2026-08": {"rows": 14270628, "stations": 5203}}, "has_actual_times": tr |

## Accepted on metadata only (open licence, machine-readable, reference data) — candidates, not used

| source | licence | formats |
|---|---|---|
| `known:bahn-vorhersage` — Bahn-Vorhersage archive (Univ. Augsburg) | ODbL-1.0 | zip |
| `govdata:haltestellen-deutsche-bahn` — Haltestellen Deutsche Bahn | CC-BY-4.0 | http://publications.europa.eu/resource/authority/file-type/csv,http://publications.europa.eu/resource/authority/file-type/geojson,http://publications.europa.eu/resource/authority/file-type/gpkg,http://publications.europa.eu/resource/authority/file-type/wms_srvc |
| `govdata:schienennetz-deutsche-bahnddea3` — Schienennetz Deutsche Bahn | CC-BY-4.0 | http://publications.europa.eu/resource/authority/file-type/csv,http://publications.europa.eu/resource/authority/file-type/geojson,http://publications.europa.eu/resource/authority/file-type/gpkg,http://publications.europa.eu/resource/authority/file-type/wms_srvc |
| `govdata:infrastrukturdaten-der-db-infrago` — Infrastrukturdaten der DB InfraGO | CC-BY-4.0 | http://publications.europa.eu/resource/authority/file-type/bin,http://publications.europa.eu/resource/authority/file-type/csv |
| `govdata:vbb-fahrplandaten-via-gtfs61e61` — VBB-Fahrplandaten via GTFS | CC-BY-4.0 | None |
| `govdata:schienennetz-und-geplante-schienenprojekte-in-der-lausitz` — Schienennetz und geplante Schienenprojekte in der Lausitz | CC-BY-4.0 | http://publications.europa.eu/resource/authority/file-type/json |
| `govdata:openstation-siri-fm-realtime-facility-status` — OpenStation SIRI FM – Realtime Facility Status | CC0-1.0 | http://publications.europa.eu/resource/authority/file-type/xml |
| `govdata:beta-openstation-netex-station-infrastructure` — OpenStation NeTEx – Static Station Infrastructure | CC0-1.0 | http://publications.europa.eu/resource/authority/file-type/xml |
| `govdata:wetterdaten-der-dwd-wetterstation-munster-osnabruck` — Wetterdaten der DWD Wetterstation Münster/Osnabrück | CC-BY-4.0 | http://publications.europa.eu/resource/authority/file-type/csv |
| `govdata:data-used-for-analysis-of-extreme-precipitation-events-and-their-impact-on-summer-deep-seepage-` — Data used for analysis of extreme precipitation events and their Impac | CC-BY-4.0 | csv |
| `govdata:wetterstation-datensatze-zu-den-luftdaten-in-konstanz-gemessen-von-lubw` — Wetterstation Datensätze zu den Luftdaten in Konstanz gemessen von LUB | CC0-1.0 | http://publications.europa.eu/resource/authority/file-type/csv |

## Rejected

| source | registry | reason |
|---|---|---|
| `known:mobilithek-delfi-gtfs` — DELFI GTFS Germany (Mobilithek) | known | needs registration or an API key: not reproducible by a stranger running timenet-build |
| `known:db-gtfs-rt` — DB GTFS-RT | known | needs registration or an API key: not reproducible by a stranger running timenet-build |
| `known:db-timetables-api` — DB Timetables (IRIS) API | known | needs registration or an API key: not reproducible by a stranger running timenet-build |
| `known:stada` — DB StaDa (station data) | known | needs registration or an API key: not reproducible by a stranger running timenet-build |
| `known:openligadb` — openligadb (football fixtures) | known | not about rail operations, weather, calendar or infrastructure (name/description) |
| `known:auma-messen` — AUMA trade-fair calendar | known | not about rail operations, weather, calendar or infrastructure (name/description) |
| `known:ticketmaster-discovery` — Ticketmaster Discovery API | known | not about rail operations, weather, calendar or infrastructure (name/description) |
| `hf:deutschebahn/mnist` — deutschebahn/mnist | huggingface | not about rail operations, weather, calendar or infrastructure (name/description) |
| `hf:islam-hajosman/deutsche_bahn_faq_1k` — islam-hajosman/deutsche_bahn_faq_1k | huggingface | not about rail operations, weather, calendar or infrastructure (name/description) |
| `hf:islam-hajosman/deutsche_bahn_faq_128` — islam-hajosman/deutsche_bahn_faq_128 | huggingface | not about rail operations, weather, calendar or infrastructure (name/description) |
| `hf:islam-hajosman/deutsche_bahn_faq_1k_emails` — islam-hajosman/deutsche_bahn_faq_1k_emails | huggingface | not about rail operations, weather, calendar or infrastructure (name/description) |
| `hf:kamalnsr123456/deutsche-bahn-data` — kamalnsr123456/deutsche-bahn-data | huggingface | temporal coverage not stated and no probe could measure it |
| `hf:ksg104/deutsche-bahn-data` — ksg104/deutsche-bahn-data | huggingface | temporal coverage not stated and no probe could measure it |
| `govdata:wfs-geoinformation-deutsches-zentrum-fur-schienenverkehrsforschung-beim-eisenbahn-bundesamt-dzs` — (WFS) Geoinformation Deutsches Zentrum für Schienenverkehrsf | govdata | format 'http://publications.europa.eu/resource/authority/file-type/bin' is not machine-readable data (map service / html / pdf) |
| `govdata:wmts-geoinformation-deutsches-zentrum-fur-schienenverkehrsforschung-beim-eisenbahn-bundesamt-dz` — (WMTS) Geoinformation Deutsches Zentrum für Schienenverkehrs | govdata | format 'http://publications.europa.eu/resource/authority/file-type/bin' is not machine-readable data (map service / html / pdf) |
| `govdata:wms-potenzielle-naturliche-gefahrdung-an-schienenwegen-des-bundes` — (WMS) Potenzielle natürliche Gefährdung an Schienenwegen des | govdata | format 'http://publications.europa.eu/resource/authority/file-type/bin' is not machine-readable data (map service / html / pdf) |
| `govdata:verkehr-krefeld` — Verkehr Krefeld | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:schienennetze-norddeutschland` — Schienennetze Norddeutschland | govdata | format 'http://publications.europa.eu/resource/authority/file-type/bin,http://publications.europa.eu/resource/authority/file-type/gml,http://publications.europa.eu/resource/authority/file-type/html' is not machine-readable data (map service / html / pdf) |
| `govdata:schienennetze-norddeutschland15266` — Schienennetze Norddeutschland | govdata | format 'gml,html,oaf,wfs,wms' is not machine-readable data (map service / html / pdf) |
| `govdata:larmkarte-essen` — Lärmkarte Essen | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:beta-boschungsbrandgefahrdung47997` — (Beta) - Böschungsbrandgefährdung | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:hochwassergefahrdung-hq100` — Hochwassergefährdung HQ100 | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:v2x-durail-funkinterferenzdaten-zwischen-stadtischen-kooperative-intelligente-verkehrssystemen-` — V2X-DuRail Funkinterferenzdaten zwischen städtischen koopera | govdata | licence 'other-closed' not in the open allowlist |
| `govdata:potentielle-hangmurena498a` — potentielle Hangmuren | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:murganggefaehrdung` — Murganggefaehrdung | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:hangrutschungsgefahrdung` — Hangrutschungsgefährdung | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:potentielle-murgange861b3` — potentielle Murgänge | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:potentielle-murgange-hangmuren` — potentielle Murgänge Hangmuren | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:flachennutzungsplan-der-kreisstadt-olpe` — Flächennutzungsplan der Kreisstadt Olpe | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:beta-boschungsbrandgefahrdung-aggregiert` — (Beta) - Böschungsbrandgefährdung aggregiert | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:murgang-und-hangmurengefahrdung-kombiniert` — Murgang- und Hangmurengefährdung kombiniert | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:mobilfunk-signalstarke-signalqualitat-fur-gsm-umts-und-lte` — Mobilfunk Signalstärke & Signalqualität für GSM, UMTS und LT | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:hangmurengefahrdung` — Hangmurengefährdung | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:bundesflachen-hamburg` — Bundesflächen Hamburg | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:bebauungsplan-wilhelmsburg-90-hamburg` — Bebauungsplan Wilhelmsburg 90 Hamburg | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:fahrplandaten-magdeburger-regionalverkehrsverbund-gmbh-marego-ohne-bahn` — Fahrplandaten Magdeburger Regionalverkehrsverbund GmbH (mare | govdata | format 'http://publications.europa.eu/resource/authority/file-type/bin' is not machine-readable data (map service / html / pdf) |
| `govdata:lvb-fahrplandaten` — LVB-Fahrplandaten | govdata | licence 'other-closed' not in the open allowlist |
| `govdata:vbb-fahrplandaten-november-2017-bis-dezember-2018` — VBB-Fahrplandaten November 2017 bis Dezember 2018 | govdata | agent judged not relevant: The dataset covers a time period from November 2017 to December 2018, which is outside the required window of November 2 |
| `govdata:vbb-fahrplandaten-via-apidb58a` — VBB-Fahrplandaten via API | govdata | licence 'other-closed' not in the open allowlist |
| `govdata:soll-fahrplandaten-mvv-regionalbus-gtfs` — Soll-Fahrplandaten MVV-Regionalbus (GTFS) | govdata | agent judged not relevant: The dataset pertains to regional bus schedules and does not provide relevant information for rail delays, cancellations, |
| `govdata:barrierefreiheit-an-bahnhofen-und-haltepunkten-spnv-baden-wurttembergf63fb` — Barrierefreiheit an Bahnhöfen und Haltepunkten (SPNV) Baden- | govdata | agent judged not relevant: The dataset focuses on accessibility at stations and does not provide information on delays, disruptions, or causes rele |
| `govdata:streckenlange-des-schienennetzes-deutschland-stichtag-betriebsordnung` — Streckenlänge des Schienennetzes: Deutschland, Stichtag, Bet | govdata | agent judged not relevant: The dataset provides information on the length of the rail network but does not include time-series data, cause codes, o |
| `govdata:streckenlange-des-schienennetzes-bundeslander-stichtag-betriebsordnung` — Streckenlänge des Schienennetzes: Bundesländer, Stichtag, Be | govdata | agent judged not relevant: The dataset provides information on the length of the rail network by federal state but does not include temporal data o |
| `govdata:streckenlange-des-schienennetzes-nach-betriebsordnung-2-land-jahr` — Streckenlänge des Schienennetzes nach Betriebsordnung (2) -L | govdata | agent judged not relevant: The dataset provides information on the length of the rail network but does not include temporal data or specific events |
| `govdata:inspire-hh-verkehrsnetze-atkis-basis-dlm51119` — INSPIRE HH Verkehrsnetze ATKIS Basis-DLM | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:inspire-hh-verkehrsnetze-alkis3f62f` — INSPIRE HH Verkehrsnetze ALKIS | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:verkehrsweg-ulr51f4b` — Verkehrsweg (ULR) | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:verkehrsweg-erweiterte-kartierung74c16` — Verkehrsweg (erweiterte Kartierung) | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:landesentwicklungsplan-hessen-inspire` — Landesentwicklungsplan Hessen INSPIRE | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:historisches-digitales-basis-landschaftsmodell-nw79824` — Historisches Digitales Basis-Landschaftsmodell NW | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:digitales-landschaftsmodell-50-nwc49b4` — Digitales Landschaftsmodell 50 NW | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:inspire-hh-verkehrsnetze-atkis-basis-dlm2a318` — INSPIRE HH Verkehrsnetze ATKIS Basis-DLM | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:inspire-hh-verkehrsnetze-alkis4788c` — INSPIRE HH Verkehrsnetze ALKIS | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:historisches-digitales-landschaftsmodell-50-nw52a25` — Historisches Digitales Landschaftsmodell 50 NW | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:digitales-basis-landschaftsmodell-nwff5f5` — Digitales Basis-Landschaftsmodell NW | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:historische-topographische-karte-nw-1-100-000` — Historische Topographische Karte NW 1:100 000 | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:digitale-topographische-karte-nw-1-10-000-historisch` — Digitale Topographische Karte NW 1:10 000, historisch | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:deutsche-grundkarte-nw-1-5-00042979` — Deutsche Grundkarte NW 1:5 000 | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:digitale-topographische-karte-nw-1-25-000-schwarz-weisscc992` — Digitale Topographische Karte NW 1:25 000 Schwarz-Weiß | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:digitale-topographische-karte-nw-1-50-000-schwarz-weiss05327` — Digitale Topographische Karte NW 1:50 000 Schwarz-Weiß | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:landesentwicklungsplan-hessen` — Landesentwicklungsplan Hessen | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:digitale-topographische-karte-nw-1-50-00032bf1` — Digitale Topographische Karte NW 1:50 000 | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:parking-information-service-db-bahnpark` — Parking Information Service - DB Bahnpark | govdata | agent judged not relevant: The dataset focuses on parking information and does not provide relevant data for rail delays, causes, or disruptions. |
| `govdata:wms-schienenverkehrsnetz-db-infrago` — WMS Schienenverkehrsnetz DB-InfraGO | govdata | format 'http://publications.europa.eu/resource/authority/file-type/bin' is not machine-readable data (map service / html / pdf) |
| `govdata:german-private-equity-barometer` — German Private Equity Barometer | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:skn-flache-nordsee-202613395` — SKN-Fläche Nordsee 2026 | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:skn-flache-nordsee-2026-wcs` — SKN-Fläche Nordsee 2026 - WCS | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:skn-flache-nordsee-2026-wms` — SKN-Fläche Nordsee 2026 - WMS | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:deutsches-kleinseen-und-teichinventar-german-small-lake-and-pond-inventory-gslpi-datensatzbe801` — Deutsches Kleinseen- und Teichinventar - German small lake a | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:land-surface-temperature-lst-aggregates-germany-summer-2021-20254a423` — Land Surface Temperature (LST) - Aggregates - Germany, Summe | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:modelldaten-ertragspotenzial-der-offshore-windenergie-fur-die-gesamte-nordsee-ausbauszenario-20511ca` — Modelldaten Ertragspotenzial der Offshore-Windenergie für di | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:modelldaten-ertragspotenzial-der-offshore-windenergie-fur-die-gesamte-nordsee-ausbausze-2025-05e7868` — Modelldaten Ertragspotenzial der Offshore-Windenergie für di | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:modelldaten-ertragspotenzial-der-offshore-windenergie-fur-die-gesamte-nordsee-ausbausze-2025-1099936` — Modelldaten Ertragspotenzial der Offshore-Windenergie für di | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:modelldaten-ertragspotenzial-der-offshore-windenergie-fur-die-gesamte-nordsee-ausbausze-2025-08a0d77` — Modelldaten Ertragspotenzial der Offshore-Windenergie für di | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:modelldaten-ertragspotenzial-der-offshore-windenergie-fur-die-gesamte-nordsee-ausbausze-2025-031a1b4` — Modelldaten Ertragspotenzial der Offshore-Windenergie für di | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:modelldaten-ertragspotenzial-der-offshore-windenergie-fur-die-gesamte-nordsee-ausbausze-2025-011cc8f` — Modelldaten Ertragspotenzial der Offshore-Windenergie für di | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:modelldaten-ertragspotenzial-der-offshore-windenergie-fur-die-gesamte-nordsee-ausbausze-2025-076d31e` — Modelldaten Ertragspotenzial der Offshore-Windenergie für di | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:modelldaten-ertragspotenzial-der-offshore-windenergie-fur-die-gesamte-nordsee-ausbausze-2025-12767ef` — Modelldaten Ertragspotenzial der Offshore-Windenergie für di | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:modelldaten-ertragspotenzial-der-offshore-windenergie-fur-die-gesamte-nordsee-ausbausze-2025-090aa6d` — Modelldaten Ertragspotenzial der Offshore-Windenergie für di | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:modelldaten-ertragspotenzial-der-offshore-windenergie-fur-die-gesamte-nordsee-ausbausze-2025-0663ee6` — Modelldaten Ertragspotenzial der Offshore-Windenergie für di | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:modelldaten-ertragspotenzial-der-offshore-windenergie-fur-die-gesamte-nordsee-ausbausze-2025-1194d2c` — Modelldaten Ertragspotenzial der Offshore-Windenergie für di | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:modelldaten-ertragspotenzial-der-offshore-windenergie-fur-die-gesamte-nordsee-ausbausze-2025-04fbe02` — Modelldaten Ertragspotenzial der Offshore-Windenergie für di | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:modelldaten-ertragspotenzial-der-offshore-windenergie-fur-die-gesamte-nordsee-ausbausze-2025-02665e1` — Modelldaten Ertragspotenzial der Offshore-Windenergie für di | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:digital-terrain-model-of-the-watercourses-elbe-and-lower-havel-germany-dgm-w-elbe-2022-project495c0` — Digital terrain model of the watercourses Elbe and Lower Hav | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:digital-surface-model-of-the-watercourses-elbe-and-lower-havel-germany-dgm-w-elbe-project-202230a12` — Digital surface model of the watercourses Elbe and Lower Hav | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:ruckstreumosaike-fk-33-2020c4718` — Rückstreumosaike - FK 33 2020 | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:ruckstreumosaike-atair-008c927f` — Rückstreumosaike - Atair 008 | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:ruckstreumosaike-atair-012acd1f` — Rückstreumosaike - Atair 012 | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:ruckstreumosaike-wega-194ed876` — Rückstreumosaike - Wega 194 | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:stundliche-stationsmessungen-der-wetterphaenomene-fur-deutschland` — Stündliche Stationsmessungen der Wetterphaenomene für Deutsc | govdata | licence 'other-closed' not in the open allowlist |
| `govdata:wettermessungen-in-der-landeshauptstadt-kiel-odala` — Wettermessungen in der Landeshauptstadt Kiel (ODALA) | govdata | licence 'other-closed' not in the open allowlist |
| `govdata:anwendung-von-digitalen-zwillingen-zur-erweiterung-der-emissionsdaten-der-beim-projekt-emidat-v-1` — Anwendung von digitalen Zwillingen zur Erweiterung der Emiss | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:dlr-urban-traffic-dataset-dlr-ut` — DLR Urban Traffic dataset (DLR UT) | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:verkehrszahlung-fahrradverkehr-daten-der-zahlstellen-munster-schlachthofviertelc9441` — Verkehrszählung Fahrradverkehr: Daten der Zählstellen Münste | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:verkehrszahlung-fahrradverkehr-daten-der-zahlstellen-munster-bahnhofsviertel9de85` — Verkehrszählung Fahrradverkehr: Daten der Zählstellen Münste | govdata | format 'http://publications.europa.eu/resource/authority/file-type/xls,xlsx' is not machine-readable data (map service / html / pdf) |
| `govdata:verkehrszahlung-fahrradverkehr-daten-der-zahlstellen-munster-josefsviertela6444` — Verkehrszählung Fahrradverkehr: Daten der Zählstellen Münste | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:verkehrszahlung-fahrradverkehr-daten-der-zahlstellen-munster-schlossbezirk131b8` — Verkehrszählung Fahrradverkehr: Daten der Zählstellen Münste | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:sentinel-5p-tropomi-aerosol-optical-depth-aod-level-3-global92426` — Sentinel-5P TROPOMI - Aerosol Optical Depth (AOD), Level 3 - | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:sentinel-5p-tropomi-water-vapour-h2o-level-3-global83503` — Sentinel-5P TROPOMI – Water Vapour (H2O), Level 3 – Global | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:bioclis-cams-wrf-germany-daily` — BioClis - CAMS/WRF - Germany, Daily | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:referenzwinddaten-langfristiges-ertragspotenzial-offshore-windenergie-ostsee-2006-serie6d962` — Referenzwinddaten langfristiges Ertragspotenzial Offshore-Wi | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:referenzwinddaten-langfristiges-ertragspotenzial-offshore-windenergie-nordsee-2006-serieae66e` — Referenzwinddaten langfristiges Ertragspotenzial Offshore-Wi | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:modelldaten-langfristiges-ertragspotenzial-offshore-windenergie-nordsee-szenario-11-2006-seriea2152` — Modelldaten langfristiges Ertragspotenzial Offshore-Windener | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:modelldaten-langfristiges-ertragspotenzial-offshore-windenergie-nordsee-szenario-7-2006-serie42925` — Modelldaten langfristiges Ertragspotenzial Offshore-Windener | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:modelldaten-langfristiges-ertragspotenzial-offshore-windenergie-nordsee-szenario-15-2006-serie66a27` — Modelldaten langfristiges Ertragspotenzial Offshore-Windener | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:modelldaten-langfristiges-ertragspotenzial-offshore-windenergie-nordsee-szenario-19-2006-serie8a74c` — Modelldaten langfristiges Ertragspotenzial Offshore-Windener | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:modelldaten-langfristiges-ertragspotenzial-offshore-windenergie-nordsee-szenario-5-2006-serie05c08` — Modelldaten langfristiges Ertragspotenzial Offshore-Windener | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:modelldaten-langfristiges-ertragspotenzial-offshore-windenergie-nordsee-szenario-16-2006-seriea1555` — Modelldaten langfristiges Ertragspotenzial Offshore-Windener | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:modelldaten-langfristiges-ertragspotenzial-offshore-windenergie-nordsee-szenario-4-2006-seriefe94e` — Modelldaten langfristiges Ertragspotenzial Offshore-Windener | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:modelldaten-langfristiges-ertragspotenzial-offshore-windenergie-nordsee-szenario-14-2006-serie0ca4f` — Modelldaten langfristiges Ertragspotenzial Offshore-Windener | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:modelldaten-langfristiges-ertragspotenzial-offshore-windenergie-nordsee-szenario-22-2006-serieb4b35` — Modelldaten langfristiges Ertragspotenzial Offshore-Windener | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:modelldaten-langfristiges-ertragspotenzial-offshore-windenergie-nordsee-szenario-25-2006-serieba99f` — Modelldaten langfristiges Ertragspotenzial Offshore-Windener | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:modelldaten-langfristiges-ertragspotenzial-offshore-windenergie-nordsee-szenario-13-2006-serie045e0` — Modelldaten langfristiges Ertragspotenzial Offshore-Windener | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:dns-reference-data-of-flow-over-periodic-hills-at-re5600-and-10595` — DNS reference data of flow over periodic hills at Re=5600 an | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:inspire-german-earthquake-catalogue-gerseis` — INSPIRE: German Earthquake Catalogue (GERSEIS) | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:global-reference-histograms-of-the-ims-infrasound-broadband-detection-lists` — Global reference histograms of the IMS infrasound broadband  | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:inspire-german-regional-seismic-network-grsn` — INSPIRE: German Regional Seismic Network (GRSN) | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:reference-percentiles-for-carotid-measures-of-subclinical-atherosclerosis-in-children-and-adole` — Reference percentiles for carotid measures of subclinical at | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:characterization-data-of-reference-industrial-polycarboxylate-superplasticizers-used-within-pri` — Characterization data of reference industrial polycarboxylat | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:open-sensor-data-for-rail-2023a97e5` — Open Sensor Data for Rail 2023 | govdata | licence 'by-sa/3.0/deed.de' not in the open allowlist |
| `govdata:grdc-caravan-extending-the-original-dataset-with-data-from-the-global-runoff-data-centre` — GRDC-Caravan: extending the original dataset with data from  | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:characterization-data-of-reference-industrial-polycarboxylate-superplasticizer-vp-2020-15-2-use` — Characterization data of reference industrial polycarboxylat | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:ship-wave-measurements-in-german-coastal-waterways-from-1998-to-2022c5954` — Ship Wave Measurements in German Coastal Waterways from 1998 | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:historical-digital-terrain-model-data-of-the-weser-estuary-hiwest11357` — Historical digital terrain model data of the Weser Estuary ( | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:co2-storage-potential-of-the-jurassic-within-the-german-central-graben` — CO2 storage potential of the Jurassic within the German Cent | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:inspire-surface-geology-geological-overview-map-of-the-german-north-sea-guk200-dn` — INSPIRE: Surface geology – Geological overview map of the Ge | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:co2-storage-potential-of-the-middle-buntsandstein-subgroup-eez-of-the-german-north-sea` — CO2 storage potential of the Middle Buntsandstein Subgroup - | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:digital-terrain-model-of-the-watercourse-estuary-elbe-2022-dgm-w-2022-model-data` — Digital terrain model of the watercourse estuary Elbe 2022 ( | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:digital-terrain-model-of-the-watercourse-estuary-elbe-2016-dgm-w-2016-model-data` — Digital terrain model of the watercourse estuary Elbe 2016 ( | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:microsatellite-ssr-dataset-pomological-and-molecular-characterization-of-apple-cultivars-malus-` — Microsatellite/SSR dataset: pomological and molecular charac | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:microsatellite-ssr-dataset-pomological-and-molecular-characterization-of-pear-cultivars-pyrus-c` — Microsatellite/SSR dataset: pomological and molecular charac | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:harmonized-cross-border-seismic-velocity-model-for-the-dutch-german-and-danish-north-sea-area-p` — Harmonized, cross-border seismic velocity model for the Dutc | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:temporal-trends-of-mercury-levels-in-fish-dab-limanda-limanda-and-sediment-from-the-german-bigh` — Temporal trends of mercury levels in fish (dab, Limanda lima | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:kinetic-measurements-used-to-determine-the-nucleophilicity-of-2-methylene-12-dihydropyridines-2` — Kinetic measurements used to determine the nucleophilicity o | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:easygsh-db_synoptische_hydrodynamik-seegangsparameter-swan8560e` — EasyGSH-DB_synoptische_Hydrodynamik: Seegangsparameter SWAN | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:stundliche-stationsmessungen-des-niederschlags-fur-deutschland` — Stündliche Stationsmessungen des Niederschlags für Deutschla | govdata | licence 'other-closed' not in the open allowlist |
| `govdata:stundliche-stationsmessungen-der-feuchteparameter-fur-deutschland` — Stündliche Stationsmessungen der Feuchteparameter für Deutsc | govdata | licence 'other-closed' not in the open allowlist |
| `govdata:stundliche-stationsmessungen-der-sichtweite-fur-deutschland` — Stündliche Stationsmessungen der Sichtweite für Deutschland | govdata | licence 'other-closed' not in the open allowlist |
| `govdata:stundliche-stationsmessungen-der-sonnenscheindauer-fur-deutschland` — Stündliche Stationsmessungen der Sonnenscheindauer für Deuts | govdata | licence 'other-closed' not in the open allowlist |
| `govdata:stundliche-stationsmessungen-der-erdbodentemperatur-fur-deutschland` — Stündliche Stationsmessungen der Erdbodentemperatur für Deut | govdata | licence 'other-closed' not in the open allowlist |
| `govdata:stundliche-stationsmessungen-des-luftdrucks-fur-deutschland` — Stündliche Stationsmessungen des Luftdrucks für Deutschland | govdata | licence 'other-closed' not in the open allowlist |
| `govdata:stundliche-stationsmessungen-der-wolkenbedeckung-fur-deutschland` — Stündliche Stationsmessungen der Wolkenbedeckung für Deutsch | govdata | licence 'other-closed' not in the open allowlist |
| `govdata:wetterdaten` — Wetterdaten | govdata | format 'http://publications.europa.eu/resource/authority/file-type/txt' is not machine-readable data (map service / html / pdf) |
| `govdata:stundliche-stationsmessungen-der-windgeschwindigkeit-und-windrichtung-fur-deutschland` — Stündliche Stationsmessungen der Windgeschwindigkeit und Win | govdata | licence 'other-closed' not in the open allowlist |
| `govdata:stundliche-stationsmessungen-der-luft-und-taupunkttemperatur-fur-deutschland` — Stündliche Stationsmessungen der Luft- und Taupunkttemperatu | govdata | licence 'other-closed' not in the open allowlist |
| `govdata:stundliche-stationsmessungen-der-lufttemperatur-und-luftfeuchte-fur-deutschland` — Stündliche Stationsmessungen der Lufttemperatur und Luftfeuc | govdata | licence 'other-closed' not in the open allowlist |
| `govdata:stundliche-stationsmessungen-der-erdbodentemperatur-in-10-cm-tiefe-in-c-fur-deutschland` — Stündliche Stationsmessungen der Erdbodentemperatur in 10 cm | govdata | licence 'other-closed' not in the open allowlist |
| `govdata:stundliche-stationsmessungen-der-solarstrahlung-global-diffus-und-der-atmospharischen-gegenstra` — Stündliche Stationsmessungen der Solarstrahlung (global/diff | govdata | licence 'other-closed' not in the open allowlist |
| `govdata:stundliche-stationsmessungen-der-wolkenbedeckung-der-wolkenart-und-der-wolkenhohe-in-bis-zu-4-s` — Stündliche Stationsmessungen der Wolkenbedeckung, der Wolken | govdata | licence 'other-closed' not in the open allowlist |
| `govdata:restni-regionalisierte-stundliche-niederschlagsdaten-fur-die-ausbreitungsrechnung-nach-ta-luft-` — RESTNI - Regionalisierte stündliche Niederschlagsdaten für d | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:gerasterte-stundliche-echtzeitdaten-der-globalstrahlung-und-der-sonnenscheindauer-basierend-auf948b5` — Gerasterte stündliche Echtzeitdaten der Globalstrahlung und  | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:gerasterte-1-km-stundliche-echtzeitdaten-der-globalstrahlung-und-der-sonnenscheindauer-basierened1a1` — Gerasterte (1 km) stündliche Echtzeitdaten der Globalstrahlu | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:5-minutige-stationsmessungen-des-niederschlages-fur-deutschland` — 5-minütige Stationsmessungen des Niederschlages für Deutschl | govdata | licence 'other-closed' not in the open allowlist |
| `govdata:flowkar-flottenwetterkarte` — FloWKar - FlottenWetterKarte | govdata | licence 'other-closed' not in the open allowlist |
| `govdata:passantenzahlung-stundendaten` — Passantenzählung - Stundendaten | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:pseudo-stationsdaten-der-stundlichen-echtzeitdaten-der-globalstrahlung-und-der-sonnenscheindaueb44b5` — Pseudo-Stationsdaten der stündlichen Echtzeitdaten der Globa | govdata | licence 'other-closed' not in the open allowlist |
| `govdata:synop-bodenwettermeldungen4e2de` — SYNOP-Bodenwettermeldungen | govdata | format 'bufr' is not machine-readable data (map service / html / pdf) |
| `govdata:realsteueristaufkommen-und-hebesatze-der-gemeinden-in-schleswig-holstein-2024-und-2025` — Realsteueristaufkommen und -hebesätze der Gemeinden in Schle | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:staatliche-steuern-in-schleswig-holstein-2025-l-i-1-j-25-sh` — Staatliche Steuern in Schleswig-Holstein 2025 (L I 1 - j 25  | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:obelisoffentlich-stamm-und-betriebsdaten-geforderter-offentlich-zuganglicher-ladestationen-fur-` — OBELISöffentlich: Stamm- und Betriebsdaten geförderter öffen | govdata | agent judged not relevant: The dataset pertains to electric vehicle charging stations and does not provide relevant information for predicting Germ |
| `govdata:statistisches-jahrbuch718de` — Statistisches Jahrbuch | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:schlusselzuweisungen-in-schleswig-holstein-2023` — Schlüsselzuweisungen in Schleswig-Holstein 2023 | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:schulen883a4` — Schulen | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:tiefbohrungen-sonstige-in-schleswig-holstein` — Tiefbohrungen (sonstige) in Schleswig-Holstein | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:tiefbohrungen-bergrecht-in-schleswig-holstein` — Tiefbohrungen (Bergrecht) in Schleswig-Holstein | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:uberschuss-der-stickstoff-flachenbilanz-der-landwirtschaft-in-den-kreisen-fur-die-jahre-1995-20` — Überschuss der Stickstoff-Flächenbilanz der Landwirtschaft i | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:daten-der-raddauerzahlstellen-munchen-2025` — Daten der Raddauerzählstellen München 2025 | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:baupreisindizes-gebaude-wagungsanteil-messz-mit-mwst-veranderung-zu-vjahr-vperiode-gebaudearten` — Baupreisindizes (Gebäude): Wägungsanteil, Messz. mit MwSt.,V | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:baupreisindizes-instandhaltung-von-wohngebauden-wagungsanteil-messzahlen-mit-mwst-bauarbeitenva` — Baupreisindizes (Instandhaltung von Wohngebäuden):Wägungsant | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:baupreisindizes-ingenieurbauten-wagungsanteilmesszahlen-mit-mwst-veranderung-zu-vorjahr-vorperi` — Baupreisindizes (Ingenieurbauten): Wägungsanteil,Messzahlen  | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:daten-der-raddauerzahlstellen-munchen-2024-1` — Daten der Raddauerzählstellen München 2024 | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:daten-der-raddauerzahlstellen-munchen-2023` — Daten der Raddauerzählstellen München 2023 | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:baustellen-hamburg-1` — Baustellen Hamburg | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:genannte-cpv-codes-in-vergebenen-offentlichen-auftragen-und-konzessionen-deutschland-quartale-a` — Genannte CPV-Codes in vergebenen öffentlichen Aufträgen und  | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:genannte-cpv-codes-in-vergebenen-offentlichen-auftragen-und-konzessionen-bundeslander-quartale-8ddbd` — Genannte CPV-Codes in vergebenen öffentlichen Aufträgen und  | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:baustellen-hamburg` — Baustellen Hamburg | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:bahnhofe1a23f` — Bahnhöfe | govdata | format 'http://publications.europa.eu/resource/authority/file-type/wfs_srvc,http://publications.europa.eu/resource/authority/file-type/wms_srvc' is not machine-readable data (map service / html / pdf) |
| `govdata:bahnhofec997b` — Bahnhöfe | govdata | format 'http://publications.europa.eu/resource/authority/file-type/wfs_srvc,http://publications.europa.eu/resource/authority/file-type/wms_srvc' is not machine-readable data (map service / html / pdf) |
| `govdata:am-bahnhof` — Am Bahnhof | govdata | format 'online' is not machine-readable data (map service / html / pdf) |
| `govdata:bahnhofe-weitere2b5b6` — Bahnhöfe, weitere | govdata | format 'http://publications.europa.eu/resource/authority/file-type/wfs_srvc,http://publications.europa.eu/resource/authority/file-type/wms_srvc' is not machine-readable data (map service / html / pdf) |
| `govdata:trilawatt-use-case-referenzdaten-und-web-gis-fur-das-msrl-berichtswesen` — TrilaWatt Use-Case: Referenzdaten und Web-GIS für das MSRL B | govdata | not about rail operations, weather, calendar or infrastructure (name/description) |
| `govdata:nr-7-bahnhof` — Nr. 7 "Bahnhof" | govdata | format 'http://publications.europa.eu/resource/authority/file-type/pdf' is not machine-readable data (map service / html / pdf) |
| `govdata:am-bahnhof-ursprungsplan-1` — Am Bahnhof (Ursprungsplan) | govdata | format 'online' is not machine-readable data (map service / html / pdf) |
| `govdata:am-bahnhof-ursprungsplan` — Am Bahnhof (Ursprungsplan) | govdata | format 'online' is not machine-readable data (map service / html / pdf) |
| `govdata:bahnhof-stuhr-ursprungsplan-1` — Bahnhof Stuhr (Ursprungsplan) | govdata | format 'online' is not machine-readable data (map service / html / pdf) |
| `govdata:bahnhof-stuhr-ursprungsplan` — Bahnhof Stuhr (Ursprungsplan) | govdata | format 'online' is not machine-readable data (map service / html / pdf) |
| `govdata:huttenbusch-am-bahnhof` — Hüttenbusch-Am Bahnhof | govdata | format 'online' is not machine-readable data (map service / html / pdf) |
| `govdata:bahnhofe-in-kielebb81` — Bahnhöfe in Kiel | govdata | temporal coverage not stated and no probe could measure it |
| `govdata:nr-7-zum-bahnhof` — Nr. 7 "Zum Bahnhof" | govdata | format 'http://publications.europa.eu/resource/authority/file-type/pdf' is not machine-readable data (map service / html / pdf) |
| `govdata:nr-2-am-bahnhof` — Nr. 2 "Am Bahnhof" | govdata | format 'http://publications.europa.eu/resource/authority/file-type/pdf' is not machine-readable data (map service / html / pdf) |
| `govdata:ostliche-anbindung-bahnhof-ursprungsplan-1` — Östliche Anbindung Bahnhof (Ursprungsplan) | govdata | format 'online' is not machine-readable data (map service / html / pdf) |
| `govdata:am-bahnhof-ii-ursprungsplan` — Am Bahnhof II (Ursprungsplan) | govdata | format 'online' is not machine-readable data (map service / html / pdf) |
| `govdata:gewerbegebiet-am-bahnhof-ursprungsplan` — Gewerbegebiet Am Bahnhof (Ursprungsplan) | govdata | format 'online' is not machine-readable data (map service / html / pdf) |
| `govdata:ostliche-anbindung-bahnhof-ursprungsplan-2` — Östliche Anbindung Bahnhof (Ursprungsplan) | govdata | format 'online' is not machine-readable data (map service / html / pdf) |
| `govdata:ostliche-anbindung-bahnhof-ursprungsplan` — Östliche Anbindung Bahnhof (Ursprungsplan) | govdata | format 'online' is not machine-readable data (map service / html / pdf) |
| `govdata:bebauungsplan-am-bahnhof-urschrift` — Bebauungsplan Am Bahnhof Urschrift | govdata | format 'online' is not machine-readable data (map service / html / pdf) |
| `govdata:am-bahnhof-mellinghausen-ursprungsplan` — Am Bahnhof (Mellinghausen) (Ursprungsplan) | govdata | format 'online' is not machine-readable data (map service / html / pdf) |
| `govdata:vor-dem-bahnhof-ursprungsplan-1` — Vor dem Bahnhof (Ursprungsplan) | govdata | format 'online' is not machine-readable data (map service / html / pdf) |
| `govdata:am-bahnhof-1-anderung-1` — Am Bahnhof (1. Änderung) | govdata | format 'online' is not machine-readable data (map service / html / pdf) |
| `govdata:am-bahnhof-1-anderung` — Am Bahnhof (1. Änderung) | govdata | format 'online' is not machine-readable data (map service / html / pdf) |
| `govdata:ostlich-des-bahnhofs-ursprungsplan-1` — Östlich des Bahnhofs (Ursprungsplan) | govdata | format 'online' is not machine-readable data (map service / html / pdf) |
| `zenodo:22730376` — Towards the Development of a Framework for Intelligent Traff | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22729809` — SPARQ: spiking physics-in-the-loop autonomous reinforcement  | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22728833` — HW-DDS: A MATLAB implementation of Holt–Winters forecasting  | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22728195` — rotation of two dipoles and according polarization response | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22727690` — Connection of imaginaries, vernaculars and affordances in cu | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22725500` — MATLAB code for "Global Stability of a Delayed Multi-Platfor | zenodo | temporal coverage not stated and no probe could measure it |
| `zenodo:22720478` — 7-Tage-Inzidenz der COVID-19-Fälle in Deutschland | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22719740` — Why Public Service Underperforms: Behavioural Governance, Mi | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22717729` — Constraint Polarity in Treasury Intermediation | zenodo | format 'pdf' is not machine-readable data (map service / html / pdf) |
| `zenodo:22715141` — Code and Data: Increased moisture recycling over the world's | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22712500` — Elevated early Eocene atmospheric CO₂ tied to reduced Southe | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22711426` — Overview of data cube technologies and review of other emerg | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22689601` — Environmental assessment in German Landscape Framework Plans | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22710543` — Global Regularity by Dissipative Topological Surgery Exact M | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22709786` — London Customs Accounts, 1380-1560: machine-readable data an | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22703601` — Data services for German marine research | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22708307` — Differential impact of mutant Ataxin-3 in hindbrain regions: | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22707711` — WeirNet: A Large-Scale 3D CFD Benchmark for Geometric Surrog | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22701493` — Regenerative Physiology in Livestock: Harnessing Stem Cells, | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22705891` — Revisiting Christ's Crucifixion & Resurrection: Pinpointing  | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22704587` — Gene Editing for ATXN3 Inactivation in Machado-Joseph diseas | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22670554` — Towards the Integration of Additive Manufacturing into a Cyb | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22703673` — Data and analysis code for: 3D-printed resin abutments are n | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22702228` — Report on data made available for research by governmental a | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22700088` — Association between postoperative pain severity and oxygen s | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22732699` — Dataset from John Wick Institutional Analysis by Audience | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22732257` — SLD reconstructed mini-DSTs from the 1996-1998 SLC runs and  | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22727240` — Joint Frontal-ear-EEG for Auditory Attention Decoding | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22732415` — SARS-CoV-2 Infektionen in Deutschland | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22732327` — TQH-C2: An Encrypted Command-and-Control Traffic Dataset Acr | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22732251` — Intercropping camphor basil shrubs with selected food crops  | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22732252` — Annotix: An Open-Source Desktop Platform for Machine Learnin | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22731317` — Structural characterization and virtual screening of Anophel | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22719139` — seqFISH spatial transcriptomic data associated with "Adm and | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22732000` — EIP Policy Firm-Year Analysis Data | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22732022` — Dataset for: DGSM, History Matching and Bayesian calibration | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22731902` — Plasma Proteome Profiles in Progressive Prostate Cancer Stat | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22731921` — Sampling Effort Data | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22730874` — Anthropogenic landscape configuration, not just composition, | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22731710` — CourtDyn: code and aggregate results for rank agreement and  | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22731727` — Submarine groundwater discharge and nutrient–carbon outwelli | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22731675` — AccessDetector: Android accessibility audit dataset (720 scr | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22731412` — Dataset for "Constraining earthquake nucleation from geodeti | zenodo | temporal coverage not stated and no probe could measure it |
| `zenodo:22731553` — Monthly Dengue, Environmental, Climatic, and Socioeconomic D | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22731539` — Supplementary Data for Edge-Intelligent Architectures and Dy | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22731474` — Supplementary datasets for: Systems-level transcriptomics re | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22715306` — Cupressus Disease Dataset | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22685033` — Global CO2 flux products from the YanDong Carbon Assimilatio | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22730896` — Italian word2vec embeddings trained on OpenSubtitles Part 2 | zenodo | format 'bz2,md,ps1' is not machine-readable data (map service / html / pdf) |
| `zenodo:22731184` — dathere/qsv: 23.0.1 | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22729931` — Emotional costs and empathy are associated with tolerance to | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22726129` — Surveillance for virus and other non-culturable pathogens in | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22726423` — Intensivkapazitäten und COVID-19-Intensivbettenbelegung in D | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22726103` — Daily streamflow substantially underestimates the severity o | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22726232` — Global Sales & Financial Performance | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22694906` — Geochemical evidence for Cambrian subduction-influenced magm | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22724933` — Daten der Notaufnahmesurveillance | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22721921` — Supplementary material 2 from: Alibrandi A, Plewka J, Vuille | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22721919` — Supplementary material 1 from: Alibrandi A, Plewka J, Vuille | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22721781` — A new short-beaked stem group cormorant (Phalacrocoracidae), | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22721757` — Reservoir fluids versus produced water as proxies for oil re | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22721581` — Challenges and impact of the farmer-scientists training prog | zenodo | format 'pdf' is not machine-readable data (map service / html / pdf) |
| `zenodo:22720492` — COVID-19-Todesfälle in Deutschland | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22720361` — COVID-19-Hospitalisierungen in Deutschland | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22714897` — PerseusDL/canonical-greekLit: 0.0.34646009516 | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22709312` — Computational Reproducibility Package for the Qattara HP-SWR | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22713034` — Syntretus (Syntretus) ocularis van Achterberg & Haeselbarth  | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22713029` — Meteorus salicorniae Schmiedeknecht 1897 | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22712049` — Streblocera (Streblocera) fulviceps Westwood 1833 | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22712039` — Perilitus stelleri | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22712035` — Perilitus rutilus | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22732354` — The 2026 AI Inflection Series, Chapter 31: The Meeting Is No | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22732301` — Cybersecurity Challenges in Nigeria's Integrated Personnel a | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22732263` — The 2026 AI Inflection Series, Chapter 30: The Authenticity  | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22732215` — The 2026 AI Inflection Series, Chapter 29: When Your Custome | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22732186` — BREAKING INTO THE RESIDENTIAL PROPERTY MARKET: DEVELOPING AN | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22732111` — The Totality Theorem: Resolution of the Closed Universe Para | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22732131` — The 2026 AI Inflection Series, Chapter 28: The Latency Tax | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22732117` — Familias contemporáneas: vínculos, cuidados y transformacion | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22732042` — The 2026 AI Inflection Series, Chapter 27: When AI Goes Offl | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22731798` — The Loudest Sound Ever Heard: Krakatau Awakens Again in a Re | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22682890` — The Rippling Field: A Spectral Framework for the Origin of R | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22731542` — Tariffs, Exemptions, and Trade Diversion: Evidence from the  | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22731276` — Analysis code and outputs: cryptocurrency designation reache | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22731072` — From Indeterminacy to Agency: Control, Subjecthood, and the  | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22730906` — A IMPORTÂNCIA DA CONTROLADORIA NA TRANSPARÊNCIA E EFICIÊNCIA | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22730815` — Asumir la diversidad social como representación de la histor | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22730476` — Riemann Minimal Entropy Collapse - A Topological Proof by Co | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22730525` — Global Authorship Across 45+ Universities in 25+ Countries,  | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22720286` — Public Utility Data Liberation Project (PUDL) Data Release | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22732414` — Split-Zero arithmetic endpoint: exact periods, determinants  | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22712850` — Resolving the Global Climate Crisis by 2037 via Decentralize | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22730564` — MQBP v6.14: An Exponential to Linear Acceleration in Quantum | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22730309` — OpenLogic in Marathi (mr-Deva-IN): Eleven Chapters with EPUB | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22726045` — Lean 4 Confirmation and Approval Proof for Hamzah Equation.  | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22723428` — Arsenic and Lead Exposure and Associated Disease Burden in B | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22722580` — El Niño in a Warming World: Understanding Intensifying Risks | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22722375` — CHAPTER 18 - Conflict Of Oaths Endangering The Union Chain | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22721232` — INFLATION TARGETING IN THE POST-PANDEMIC ERA: CHALLENGES AND | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22721058` — Road network disruption | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22720207` — Effectiveness of AI-Generated Study Materials versus Traditi | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22713669` — L'Ange des projections lumineuses: Transcription of the Ten  | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22711646` — scworkbench cross-operator continuity experiments: evidence  | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22700797` — scworkbench v0.1.0 preprint software artifacts | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22710619` — A Derived Reciprocity Moduli Principle: A Conjectural Synthe | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22732112` — Analysis code for "Losing my religion? An aggregation parado | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22732513` — Data and Codes for Reply to Comment on E-DeepGS | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22732338` — Testing reaction-network inference from aerosol molecular ti | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22732208` — SANOAT KOMPANIYALARINING DAVLAT XARIDLARIDA NARX SHAKLLANISH | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22732377` — NoiBic: A Noise-Tolerant Biclustering Algorithm for High-Thr | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:19834242` — Data, scripts and outputs for the Bayesian Brownian Bridge d | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22119474` — Gamma Waves as a Biomarker for Coherence and Its Loss in Cog | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22732245` — The Completed Civilization: Finishing the Arrested Holon | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22732164` — space_packet_parser | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22732497` — Luminous Behavioral Economics: The Translation Layer Between | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22732228` — The Millennium Riemann Hypothesis: Resolution via Log-Concav | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22732213` — reflectivity/reflectivity.github.io: Release 2026-09-13-04-2 | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22731989` — La frontera de Bell es escalar vs. vectorial | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22732018` — Pierre Deligne — Collected Papers: English and French Editio | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22732133` — Livestock Production Interventions, Pastoral Resilience, and | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22731836` — Beyond Gametocyte Density: Sex-Structured Reproductive Avail | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22731761` — Evaluating the Observed Advantage of Tool-Evidence Fusion un | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22731786` — Code and derived tables for: Cells are not replicates - perm | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22732105` — The Cholinergic Floor: The Organ Beneath Everything (Second  | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22731266` — The Human Intellectual Idea Stamp: A Proposal to Record Huma | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22730634` — Challenges in the Use of Social Media among Students of Nige | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22730388` — Reproducibility materials for ECMX-D-26-01378: Resource-Expl | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22730280` — Tools CoS | WP5 | M5.1 Workflow Management Plan | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22669107` — #RSAA26 Building Capacity from the Inside: A Project Update  | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22730291` — Evaluating the Integration of Innovative Technologies in Lib | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22729821` — Example data for scanarea: projected plant area estimation f | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22730058` — Tools CoS | WP4 | M4.1 Selection of two communities from wit | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22729785` — Micro-XRF characterization of elemental mixing and diffusion | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22729918` — HCTGS v28 Morocco: The Atlas Gateway v2 | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22170944` — Data and codes in support of "Inland battery shipping as the | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
