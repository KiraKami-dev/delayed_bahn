import { useEffect, useState } from "react"

function readMotionOff(): boolean {
  try {
    const q = new URLSearchParams(location.search)
    if (q.get("motion") === "0") return true
    if (document.documentElement.dataset.motion === "0") return true
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches
  } catch {
    return false
  }
}

let listeners = new Set<() => void>()
export function toggleMotion() {
  const off = document.documentElement.dataset.motion === "0"
  if (off) delete document.documentElement.dataset.motion
  else document.documentElement.dataset.motion = "0"
  listeners.forEach((l) => l())
}

export function useReducedMotion(): boolean {
  const [off, setOff] = useState(readMotionOff)
  useEffect(() => {
    const update = () => setOff(readMotionOff())
    listeners.add(update)
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)")
    mq.addEventListener("change", update)
    return () => {
      listeners.delete(update)
      mq.removeEventListener("change", update)
    }
  }, [])
  return off
}

export function motionOff(): boolean {
  return readMotionOff()
}

export const DUR = { fly: 2400, leg: 700, count: 1200 } as const
