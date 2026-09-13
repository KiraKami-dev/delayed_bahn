# Source assessment

Generated 2026-09-13 05:15 UTC over window 2025-11-02..2026-08-31. 150 candidates from four registries (known list, HuggingFace, govdata CKAN, Zenodo); 22 passed every gate (7 probed live, 15 accepted on metadata only and not used), 128 rejected. Every verdict is a deterministic predicate; the reason is the first gate that failed.

## Accepted and probed live

| source | kind | licence | role | what the probe measured |
|---|---|---|---|---|
| `known:piebro/deutsche-bahn-data` | events | CC-BY-4.0 | primary series | {"n_columns": 18, "per_month": {"2025-10": {"rows": 1989180, "stations": 107}, "2025-11": {"rows": 13943561, "stations": 5293}, "2026-08": {"rows": 14270628, "stations": 5203}}, "has_actual_times": tr |
| `known:openholidays` | calendar | ODbL-1.0 | annotations | {"school_periods_BY": 7, "public_holidays_BY": 13} |
| `known:db-stations` | reference | ISC | annotations / join hub | {"stations": 5388} |
| `known:bright-sky` | weather | DL-DE-BY-2.0 | context annotations or channels | {"hourly_rows_one_week": 169} |
| `known:infrago-infrastruktur` | infrastructure | CC-BY-4.0 | annotations | {"size_mb": null} |
| `known:zensus-2022-grid` | reference | DL-DE-BY-2.0 | annotations / join hub | {"size_mb": null} |
| `hf:piebro/deutsche-bahn-data` | unknown | CC-BY-4.0 | unknown | {"n_columns": 18, "per_month": {"2025-10": {"rows": 1989180, "stations": 107}, "2025-11": {"rows": 13943561, "stations": 5293}, "2026-08": {"rows": 14270628, "stations": 5203}}, "has_actual_times": tr |

## Accepted on metadata only (open licence, machine-readable, reference data) — candidates, not used

| source | licence | formats |
|---|---|---|
| `known:bahn-vorhersage` — Bahn-Vorhersage archive (Univ. Augsburg) | ODbL-1.0 | zip |
| `govdata:haltestellen-deutsche-bahn` — Haltestellen Deutsche Bahn | CC-BY-4.0 | http://publications.europa.eu/resource/authority/file-type/csv,http://publications.europa.eu/resource/authority/file-type/geojson,http://publications.europa.eu/resource/authority/file-type/gpkg,http://publications.europa.eu/resource/authority/file-type/wms_srvc |
| `govdata:schienennetz-deutsche-bahnddea3` — Schienennetz Deutsche Bahn | CC-BY-4.0 | http://publications.europa.eu/resource/authority/file-type/csv,http://publications.europa.eu/resource/authority/file-type/geojson,http://publications.europa.eu/resource/authority/file-type/gpkg,http://publications.europa.eu/resource/authority/file-type/wms_srvc |
| `govdata:infrastrukturdaten-der-db-infrago` — Infrastrukturdaten der DB InfraGO | CC-BY-4.0 | http://publications.europa.eu/resource/authority/file-type/bin,http://publications.europa.eu/resource/authority/file-type/csv |
| `govdata:vbb-fahrplandaten-via-gtfs61e61` — VBB-Fahrplandaten via GTFS | CC-BY-4.0 | None |
| `govdata:vbb-fahrplandaten-november-2017-bis-dezember-2018` — VBB-Fahrplandaten November 2017 bis Dezember 2018 | CC-BY-4.0 | zip |
| `govdata:soll-fahrplandaten-mvv-regionalbus-gtfs` — Soll-Fahrplandaten MVV-Regionalbus (GTFS) | CC-BY-4.0 | http://publications.europa.eu/resource/authority/file-type/zip |
| `govdata:barrierefreiheit-an-bahnhofen-und-haltepunkten-spnv-baden-wurttembergf63fb` — Barrierefreiheit an Bahnhöfen und Haltepunkten (SPNV) Baden-Württember | DL-DE-BY-2.0 | http://publications.europa.eu/resource/authority/file-type/csv,http://publications.europa.eu/resource/authority/file-type/pdf,http://publications.europa.eu/resource/authority/file-type/zip |
| `govdata:streckenlange-des-schienennetzes-deutschland-stichtag-betriebsordnung` — Streckenlänge des Schienennetzes: Deutschland, Stichtag, Betriebsordnu | DL-DE-BY-2.0 | http://publications.europa.eu/resource/authority/file-type/csv,http://publications.europa.eu/resource/authority/file-type/xml |
| `govdata:streckenlange-des-schienennetzes-bundeslander-stichtag-betriebsordnung` — Streckenlänge des Schienennetzes: Bundesländer, Stichtag, Betriebsordn | DL-DE-BY-2.0 | http://publications.europa.eu/resource/authority/file-type/csv,http://publications.europa.eu/resource/authority/file-type/xml |
| `govdata:schienennetz-und-geplante-schienenprojekte-in-der-lausitz` — Schienennetz und geplante Schienenprojekte in der Lausitz | CC-BY-4.0 | http://publications.europa.eu/resource/authority/file-type/json |
| `govdata:streckenlange-des-schienennetzes-nach-betriebsordnung-2-land-jahr` — Streckenlänge des Schienennetzes nach Betriebsordnung (2) -Land - Jahr | DL-DE-BY-2.0 | http://publications.europa.eu/resource/authority/file-type/csv,http://publications.europa.eu/resource/authority/file-type/xml |
| `govdata:parking-information-service-db-bahnpark` — Parking Information Service - DB Bahnpark | DL-DE-BY-2.0 | http://publications.europa.eu/resource/authority/file-type/json |
| `govdata:openstation-siri-fm-realtime-facility-status` — OpenStation SIRI FM – Realtime Facility Status | CC0-1.0 | http://publications.europa.eu/resource/authority/file-type/xml |
| `govdata:beta-openstation-netex-station-infrastructure` — OpenStation NeTEx – Static Station Infrastructure | CC0-1.0 | http://publications.europa.eu/resource/authority/file-type/xml |

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
| `govdata:vbb-fahrplandaten-via-apidb58a` — VBB-Fahrplandaten via API | govdata | licence 'other-closed' not in the open allowlist |
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
| `govdata:wms-schienenverkehrsnetz-db-infrago` — WMS Schienenverkehrsnetz DB-InfraGO | govdata | format 'http://publications.europa.eu/resource/authority/file-type/bin' is not machine-readable data (map service / html / pdf) |
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
| `zenodo:22732415` — SARS-CoV-2 Infektionen in Deutschland | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22732343` — Dataset from John Wick Institutional Analysis by Audience | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
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
| `zenodo:22730917` — MI-Snow1000 reviewer deposit | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
| `zenodo:22699408` — Reproducibility data for "Beyond Bonding Evolution Sequences | zenodo | not about rail operations, weather, calendar or infrastructure (name/description) |
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
