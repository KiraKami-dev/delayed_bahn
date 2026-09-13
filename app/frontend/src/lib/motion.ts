import { useEffect, useState } from "react"

// Motion is off unless the traveller switches it on (the play button, or ?motion=1): the moving
// map pulls the eye away from reading the forecast. The button's choice wins over the URL.
function readMotionOff(): boolean {
  try {
    const setting = document.documentElement.dataset.motion
    if (setting === "1") return false
    if (setting === "0") return true
    return new URLSearchParams(location.search).get("motion") !== "1"
  } catch {
    return true
  }
}

let listeners = new Set<() => void>()
export function toggleMotion() {
  document.documentElement.dataset.motion = readMotionOff() ? "1" : "0"
  listeners.forEach((l) => l())
}

export function useReducedMotion(): boolean {
  const [off, setOff] = useState(readMotionOff)
  useEffect(() => {
    const update = () => setOff(readMotionOff())
    listeners.add(update)
    return () => {
      listeners.delete(update)
    }
  }, [])
  return off
}

export function motionOff(): boolean {
  return readMotionOff()
}

export const DUR = { fly: 2400, leg: 700, count: 1200 } as const
