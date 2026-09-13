import { ArrowLeft, ArrowRight, ArrowUpRight, Check, ChevronDown, CircleHelp, Clock3, Info, Leaf, Loader2, MapPin, MoveUpRight, Pause, Play, Route, ShieldCheck, TrainFront, X } from "lucide-react"
import { lazy, Suspense, useEffect, useRef, useState } from "react"
import { useStore } from "@/lib/store"
import { fmtDate, fmtTime } from "@/lib/geo"
import { toggleMotion, useReducedMotion } from "@/lib/motion"
import { StartPanel } from "@/features/share-parser/components/StartPanel"
import { JourneyCards } from "@/features/share-parser/components/JourneyCards"
import { ForecastPanel } from "@/features/delay-prediction/components/ForecastPanel"
import { AdvicePanel, LeaveHomeBy, travelerAdvice } from "@/features/recommendation/components/AdvicePanel"
import { CausesPanel } from "@/features/causes/components/CausesPanel"
import { EvidencePanel } from "@/features/evidence/components/EvidencePanel"
import { WhyDisclosure } from "@/features/delay-prediction/components/WhyDisclosure"
import { TabBar } from "./TabBar"
import { InstallButton, OfflinePill } from "./StatusPills"
import { STAGE_STEPS } from "../hooks/useStageKeys"

const GlobeMap = lazy(() => import("@/features/globe-map/components/GlobeMap").then(m => ({ default: m.GlobeMap })))

function JourneyOutlook() {
  const s = useStore()
  const p = s.prediction
  if (!p) return null
  const risk = p.planFailProbability.value
  const direct = s.journey?.legs.length === 1
  const delay = p.legs.at(-1)?.expectedDelayMinutes
  const tone = direct ? "low" : risk < 0.15 ? "low" : risk < 0.4 ? "mid" : "high"
  const title = direct ? "One train. No changes to make." : tone === "low" ? "A little more peace of mind." : tone === "mid" ? "Give yourself a little more time." : "This connection needs a backup plan."
  return (
    <section className="outlook-card" data-risk={tone} aria-labelledby="outlook-heading">
      <div className="eyebrow"><ShieldCheck size={15} /><h2 id="outlook-heading">Your connection outlook</h2></div>
      <div className="outlook-main"><h3>{title}</h3><div className="outlook-number">{direct ? `+${Math.round(delay?.value ?? 0)}` : `${Math.round(risk * 100)}%`}<span>{direct ? "minutes estimated arrival delay" : "estimated plan-failure risk"}</span></div></div>
      <p>{direct ? "There’s no connection to miss, but your train can still arrive late. This delay estimate is not a guarantee; check live departures before traveling." : s.recommendation ? travelerAdvice(s.recommendation) : "See the train-by-train forecast below. Connection estimates are not a guarantee of arrival."}</p>
      <div className="outlook-footer"><WhyDisclosure item={direct && delay ? delay : p.planFailProbability} label="What’s behind this estimate?" /><button type="button" onClick={() => s.dispatch({ type: "tab", tab: "advice" })}>Your next steps <ArrowRight size={15} /></button></div>
    </section>
  )
}

function RouteView() {
  const s = useStore()
  const [visible, setVisible] = useState(() => window.matchMedia("(min-width: 1024px)").matches)
  if (!s.journey) return null
  return (
    <section className="route-card" aria-label="Journey visualization">
      <div className="route-heading"><div><span className="eyebrow">THE BIG PICTURE</span><h2>Your journey, connected.</h2></div><button className="icon-button" type="button" aria-expanded={visible} aria-label={visible ? "Hide 3D route" : "Show 3D route"} onClick={() => setVisible(!visible)}><ChevronDown size={20} className={visible ? "rotate-180" : ""} /></button></div>
      {visible && <div className="map-frame"><Suspense fallback={<div className="map-placeholder"><Loader2 size={24} className="animate-spin" /> Opening your route…</div>}><GlobeMap /></Suspense></div>}
      <div className="route-stops">
        {s.journey.legs.map((leg, i) => <button key={i} type="button" aria-pressed={s.selectedLeg === i} onClick={() => { s.dispatch({ type: "selectLeg", index: s.selectedLeg === i ? null : i }); setVisible(true) }}><span className="stop-dot">{i + 1}</span><span><strong>{leg.from.name}</strong><small>{fmtTime(leg.plannedDeparture)} · {leg.trainId}</small></span><MoveUpRight size={15} /></button>)}
        <div className="destination-stop"><span className="stop-dot"><MapPin size={14} /></span><span><strong>{s.journey.legs.at(-1)?.to.name}</strong><small>{fmtTime(s.journey.legs.at(-1)!.plannedArrival)} · scheduled arrival</small></span></div>
      </div>
      <p className="map-note">Route lines connect stations, not actual tracks. All times are local to Germany.</p>
    </section>
  )
}

export function AppShell() {
  const s = useStore()
  const still = useReducedMotion()
  const dialog = useRef<HTMLDialogElement>(null)
  const main = useRef<HTMLElement>(null)
  const [help, setHelp] = useState<"how" | "evidence">("how")
  const [imageFailed, setImageFailed] = useState(false)
  const first = s.journey?.legs[0]
  const last = s.journey?.legs.at(-1)
  const isDemo = s.journey?.source === "seed"
  const isPrior = s.prediction?.modelId.toLowerCase().includes("mock") || s.prediction?.modelId.toLowerCase().includes("prior")
  const openHelp = (section: "how" | "evidence") => { setHelp(section); dialog.current?.showModal() }

  useEffect(() => {
    if (s.journey) main.current?.focus({ preventScroll: true })
  }, [s.journey?.id])

  return (
    <div className="shell">
      <a className="skip-link" href="#main-content">Skip to trip planner</a>
      <header className="site-header">
        <a className="brand" href="/" aria-label="error404 home"><span className="brand-mark"><TrainFront size={22} strokeWidth={1.8} /></span><span>error<span className="brand-digits">404</span><small>A clearer way to travel.</small></span></a>
        <nav className="header-nav" aria-label="Main navigation"><a href="#main-content" className="nav-active">Check a trip</a><button type="button" onClick={() => openHelp("how")}>How it works</button><button type="button" onClick={() => openHelp("evidence")} className="about-link">About our estimates <ArrowUpRight size={13} /></button></nav>
        <div className="header-tools"><OfflinePill /><InstallButton /><span className="rail-badge"><span /> Built for DB journeys</span></div>
      </header>

      <main id="main-content" ref={main} tabIndex={-1}>
        {!s.journey ? (
          <div className="landing-layout">
            <div className="landing-content">
              <div className="eyebrow hero-eyebrow"><span className="little-line" /> A LITTLE CERTAINTY, EVERY JOURNEY</div>
              <h1>Less “will I make it?”<br /><span>More “I’m on my way.”</span></h1>
              <p className="hero-description">A tight change shouldn’t take over your trip. Check your Deutsche Bahn journey, understand the risks, and travel with a plan.</p>
              {s.error && <div role="alert" className="error-banner"><Info size={18} /><div><strong>We couldn’t complete your check.</strong><p>{s.error}</p></div></div>}
              <StartPanel />
            </div>
            <div className="landing-visual">
              <div className="scenic-art" data-still={still} onPointerMove={e => {
                if (still || e.pointerType !== "mouse") return
                const r = e.currentTarget.getBoundingClientRect()
                e.currentTarget.style.setProperty("--tilt-x", `${((e.clientY - r.top) / r.height - 0.5) * -4}deg`)
                e.currentTarget.style.setProperty("--tilt-y", `${((e.clientX - r.left) / r.width - 0.5) * 5}deg`)
              }} onPointerLeave={e => { e.currentTarget.style.setProperty("--tilt-x", "0deg"); e.currentTarget.style.setProperty("--tilt-y", "0deg") }}>
                <div className="scene-orbit" aria-hidden="true" />
                {!imageFailed ? <img src="/rail-landscape.svg" alt="A miniature white train winding through a green European landscape" width="1536" height="1152" fetchPriority="high" onError={() => setImageFailed(true)} /> : <div className="scenic-fallback" aria-hidden="true"><TrainFront size={100} strokeWidth={0.8} /><span>A clearer way to travel.</span></div>}
                <div className="scene-tag"><span className="scene-tag-icon"><Leaf size={19} /></span><span>Take the scenic route.<small>Leave the guesswork behind.</small></span></div>
                <div className="scene-caption">A little perspective for the journey ahead.</div>
              </div>
              <div className="benefit-grid"><div><span className="benefit-icon"><Route size={21} /></span><h3>Every connection.</h3><p>Understand how one train’s delay affects the next.</p></div><div><span className="benefit-icon"><Clock3 size={21} /></span><h3>A plan, not a puzzle.</h3><p>Know where extra time can make a difference.</p></div><div><span className="benefit-icon"><ShieldCheck size={21} /></span><h3>No false promises.</h3><p>Clear estimates, honest limitations. You stay in control.</p></div></div>
            </div>
          </div>
        ) : (
          <div className="journey-page">
            <button className="back-button" type="button" onClick={() => s.dispatch({ type: "reset" })}><ArrowLeft size={16} /> Check another trip</button>
            <div className="journey-page-heading"><div><div className="eyebrow">YOUR JOURNEY, WITH A LITTLE MORE CLARITY</div><h1>{first?.from.name}<ArrowRight aria-label="to" />{last?.to.name}</h1><p>{first && fmtDate(first.plannedDeparture)}<span>·</span>{first && fmtTime(first.plannedDeparture)} – {last && fmtTime(last.plannedArrival)}<span>·</span>{s.journey.legs.length - 1} {s.journey.legs.length === 2 ? "change" : "changes"}</p></div><span className="journey-pill"><TrainFront size={16} /> {isDemo ? "Example journey" : "Your DB journey"}</span></div>
            {(isDemo || isPrior) && <div className="data-notice"><Info size={18} /><div><strong>{isDemo ? "Example trip · not live travel advice" : "Illustrative estimate · no live delay data"}</strong><p>{isDemo ? "Explore the experience with a saved example. Its dates, forecast and alternatives are for demonstration only." : "The backend returned a statistical prior, not a live or fine-tuned forecast. Confirm current times and connections in DB Navigator."}</p></div></div>}
            {s.error && <div className="error-banner" role="alert"><Info size={18} /><div><strong>Your journey is saved in this session.</strong><p>{s.error}</p><button type="button" className="text-button" disabled={s.busy} onClick={() => void s.runJourney(s.journey!)}>Try the check again <ArrowRight size={14} /></button></div></div>}
            {s.busy && <div className="progress-notice" role="status"><Loader2 size={18} className="animate-spin" />{s.stage === "recommending" ? "Finding useful next steps…" : "Checking each train and connection…"}</div>}
            <div className="results-layout"><div className="results-main"><JourneyOutlook /><TabBar /><div className="tab-content" id="journey-panel">
              {s.tab === "plan" && <><JourneyCards journey={s.journey} />{s.recommendation && <LeaveHomeBy rec={s.recommendation} />}</>}
              {s.tab === "forecast" && <ForecastPanel />}
              {s.tab === "advice" && <AdvicePanel />}
              {s.tab === "causes" && <CausesPanel />}
              {s.tab === "evidence" && <EvidencePanel />}
            </div><p className="travel-disclaimer"><Info size={14} /> Estimates help you plan; they do not guarantee an arrival time. Check live departures and platforms in DB Navigator before traveling.</p></div><RouteView /></div>
          </div>
        )}
      </main>

      <footer className="site-footer"><div><span className="footer-mark"><TrainFront size={16} /> error404</span><span>Made for the journey. Not the worry.</span></div><div><span>Independent companion · not affiliated with Deutsche Bahn</span><button type="button" className="motion-button" aria-label={still ? "Enable visual motion" : "Pause visual motion"} aria-pressed={still} onClick={toggleMotion}>{still ? <Play size={13} /> : <Pause size={13} />}{still ? "Motion off" : "Pause motion"}</button></div></footer>
      {s.stageMode && <div className="stage-dots" aria-label={`Step ${s.stageStep + 1} of ${STAGE_STEPS.length}`}><span>{STAGE_STEPS[s.stageStep]?.label}</span><button type="button" aria-label="Exit presentation mode" onClick={() => s.dispatch({ type: "stageMode", on: false })}><X size={16} /></button></div>}

      <dialog ref={dialog} className="help-dialog" aria-labelledby="help-title" onClick={e => { if (e.target === e.currentTarget) dialog.current?.close() }}>
        <div className="dialog-inner"><div className="dialog-heading"><span className="icon-tile"><CircleHelp size={22} /></span><button type="button" className="icon-button" aria-label="Close help" onClick={() => dialog.current?.close()}><X size={20} /></button></div><h2 id="help-title">{help === "how" ? "A clearer journey in three steps." : "Good decisions start with honest estimates."}</h2>
          {help === "how" ? <><ol className="how-steps"><li><span>01</span><div><h3>Bring your journey.</h3><p>Open a connection in DB Navigator, choose Share, then paste the full text here. A booking link alone won’t contain the train details.</p></div></li><li><span>02</span><div><h3>See the connections that matter.</h3><p>We check individual train delays and how they could affect your changes. Look at the data notice to see whether the result uses example data, a prior, or a model forecast.</p></div></li><li><span>03</span><div><h3>Choose your next step.</h3><p>Review your transfer time and advice, then confirm schedules and any alternative in DB Navigator. This app does not book or change tickets.</p></div></li></ol><div className="install-note"><Check size={18} /><div><strong>Keep it close for your next trip.</strong><p>On Android, install from Chrome to share directly into error404. On iPhone, use Safari’s Add to Home Screen and paste your journey.</p><InstallButton /></div></div></> : <EvidencePanel />}
        </div>
      </dialog>
    </div>
  )
}
