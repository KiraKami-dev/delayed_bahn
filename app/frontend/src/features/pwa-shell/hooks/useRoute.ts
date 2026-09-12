import { useEffect, useState } from "react"

export type Route = { path: string; params: URLSearchParams }

function read(): Route {
  return { path: location.pathname, params: new URLSearchParams(location.search) }
}

export function useRoute(): Route {
  const [route, setRoute] = useState<Route>(read)
  useEffect(() => {
    const onPop = () => setRoute(read())
    window.addEventListener("popstate", onPop)
    return () => window.removeEventListener("popstate", onPop)
  }, [])
  return route
}

export function replaceUrl(path: string) {
  history.replaceState(null, "", path)
}
