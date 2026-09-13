import * as THREE from 'three'
import { MercatorCoordinate, type CustomLayerInterface, type Map } from 'maplibre-gl'
import type { Journey, Prediction } from '@/lib/contract'
import { trainDelay, trainScale, disruptionKind, buildStory, storyState, type LegPhase } from '@/lib/train-story'
import { motionOff } from '@/lib/motion'
import { trainVisual } from '@/lib/train-service'
import { buildTrack, sampleTrack, validTrack } from '@/lib/track-path'
import { legLine } from '@/lib/geo'
import { buildCar, buildLabel, carCount, sceneWith, CAR_LENGTH, CAR_PITCH } from './train-models'

export type TrainHead = { lon: number; lat: number; heading: number; leg: number; phase: LegPhase; trackLength: number }
export type TrainLayer = CustomLayerInterface & { head(): TrainHead | null }

// Exaggerated miniature trains, not live vehicle positions. Uses the map's own
// globe/mercator projection so models stay attached during the camera flight.
export function createTrainLayer(journey: Journey, prediction?: Prediction): TrainLayer {
  let renderer: THREE.WebGLRenderer
  let map: Map
  const camera = new THREE.Camera()
  type Track = ReturnType<typeof buildTrack>
  type Asset = { scene: THREE.Scene; track: Track; leg: number; car: number; cars: number; fixed?: boolean }
  const assets: Asset[] = []
  const tracks: (Track | undefined)[] = journey.legs.map(leg => {
    const line = validTrack(leg.routeGeometry) ? leg.routeGeometry : legLine(leg)
    return line && validTrack(line) ? buildTrack(line) : undefined
  })
  const story = buildStory(journey, prediction, tracks.map(track => track?.length ?? 0))
  let elapsed = 0, lastFrame: number | undefined
  let head: TrainHead | null = null
  const resume = () => { lastFrame = undefined; if (!document.hidden) map?.triggerRepaint() }
  const box = (group: THREE.Group, size: [number, number, number], position: [number, number, number], color: string) => {
    const mesh = new THREE.Mesh(new THREE.BoxGeometry(...size), new THREE.MeshStandardMaterial({ color, roughness: .45 }))
    mesh.position.set(...position); group.add(mesh)
  }
  journey.legs.forEach((leg, index) => {
    const track = tracks[index]
    if (!track) return
    const style = trainVisual(leg)
    const delay = trainDelay(journey, leg, index, prediction)
    const cars = carCount(style.kind)
    for (let car = 0; car < cars; car++) {
      const model = buildCar(style, car, cars)
      if (car === 0) {
        model.add(buildLabel(`${leg.trainId} · ${delay == null ? 'no delay estimate' : `+${Math.round(delay)} min estimated`}`, delay && delay > 5 ? '#9a4514ee' : '#1f4a3fee', 2.7))
        if (delay != null && delay > 0) {
          const ring = new THREE.Mesh(new THREE.TorusGeometry(1.1, .08, 8, 40), new THREE.MeshBasicMaterial({ color: '#f7a629', transparent: true, opacity: .8 }))
          ring.rotation.x = Math.PI / 2; ring.position.y = .06; model.add(ring)
        }
      }
      assets.push({ scene: sceneWith(model), track, leg: index, car, cars })
    }
    const notice = leg.disruptions?.find(item => item.text.trim() && item.source.trim())
    if (notice) {
      const obstacle = new THREE.Group()
      const kind = disruptionKind(notice.text)
      if (kind === 'weather') {
        for (let i = 0; i < 3; i++) {
          const cloud = new THREE.Mesh(new THREE.SphereGeometry(.5, 12, 10), new THREE.MeshStandardMaterial({ color: '#849caa' }))
          cloud.position.set((i - 1) * .5, 1.5, 0); obstacle.add(cloud)
          box(obstacle, [.05, .5, .05], [(i - 1) * .5, .6, 0], '#57b5e2')
        }
      } else if (kind === 'works') {
        box(obstacle, [2.8, .45, .18], [0, 1, 0], '#f29536')
        for (let i = -1; i <= 1; i++) box(obstacle, [.3, .47, .2], [i * .85, 1, 0], '#fff2dc')
        for (const x of [-1, 1]) box(obstacle, [.15, 1.2, .2], [x, .6, 0], '#344a43')
      } else {
        box(obstacle, [.16, 1.5, .16], [0, .75, 0], '#344a43')
        box(obstacle, [.75, .75, .22], [0, 1.5, 0], kind === 'technical' ? '#d25337' : '#d38d29')
      }
      obstacle.add(buildLabel(`${leg.trainId} · ${kind === 'reported' ? 'service notice' : `reported ${kind}`}`, '#6a3d1cee', 2.7))
      obstacle.add(buildLabel('Illustrative location · see notice', '#3a4f46ee', 3.8))
      assets.push({ scene: sceneWith(obstacle), track, leg: index, car: 0, cars: 1, fixed: true })
    }
  })
  const stillState = { legs: journey.legs.map(() => ({ progress: .5, phase: 'moving' as const })), active: 0 }
  return {
    id: 'journey-miniatures', type: 'custom', renderingMode: '3d',
    head: () => head,
    onAdd(m, gl) {
      map = m
      renderer = new THREE.WebGLRenderer({ canvas: m.getCanvas(), context: gl as WebGL2RenderingContext, antialias: true })
      renderer.autoClear = false
      document.addEventListener("visibilitychange", resume)
    },
    render(_gl, args) {
      const moving = !motionOff() && !document.hidden
      const now = performance.now()
      if (moving && lastFrame != null) elapsed += Math.min(100, now - lastFrame)
      lastFrame = now
      const state = moving || elapsed > 0 ? storyState(story, elapsed) : stillState
      const zoom = map.getZoom()
      const globe = args.defaultProjectionData.projectionTransition > 0
      let nextHead: TrainHead | null = null
      for (const asset of assets) {
        const scale = trainScale(zoom, asset.track.length)
        const legState = state.legs[asset.leg]
        const trainLength = (asset.cars * CAR_PITCH - (CAR_PITCH - CAR_LENGTH)) * scale
        // The head sits at the story position; a waiting train stands fully inside its platform.
        const headDistance = asset.fixed ? asset.track.length * .7 : Math.max(Math.min(trainLength, asset.track.length), legState.progress * asset.track.length)
        const distance = headDistance - (asset.car * CAR_PITCH + CAR_LENGTH / 2) * scale
        if (distance < 0) continue
        const { point: [lon, lat], heading } = sampleTrack(asset.track, distance)
        if (!asset.fixed && asset.car === 0 && asset.leg === state.active) nextHead = { lon, lat, heading, leg: asset.leg, phase: legState.phase, trackLength: asset.track.length }
        let model: THREE.Matrix4
        if (globe) {
          model = new THREE.Matrix4().makeRotationY(lon * Math.PI / 180)
            .multiply(new THREE.Matrix4().makeRotationX(-lat * Math.PI / 180))
            .multiply(new THREE.Matrix4().makeTranslation(0, 0, 1.00001))
            .multiply(new THREE.Matrix4().makeRotationX(Math.PI / 2))
            .scale(new THREE.Vector3(1 / 6371008.8, 1 / 6371008.8, 1 / 6371008.8))
        } else {
          const merc = MercatorCoordinate.fromLngLat([lon, lat], 15)
          const unit = merc.meterInMercatorCoordinateUnits()
          model = new THREE.Matrix4().makeTranslation(merc.x, merc.y, merc.z)
            .multiply(new THREE.Matrix4().makeRotationZ(Math.PI))
            .multiply(new THREE.Matrix4().makeRotationX(Math.PI / 2))
            .scale(new THREE.Vector3(-unit, unit, unit))
        }
        model.scale(new THREE.Vector3(scale, scale, scale))
        // Local +Z points south in the map transform; convert compass heading.
        model.multiply(new THREE.Matrix4().makeRotationY(Math.PI - heading))
        camera.projectionMatrix.fromArray(args.defaultProjectionData.mainMatrix).multiply(model)
        renderer.resetState(); renderer.render(asset.scene, camera)
      }
      head = nextHead
      if (moving && assets.length) map.triggerRepaint()
    },
    onRemove() {
      document.removeEventListener("visibilitychange", resume)
      assets.forEach(({ scene }) => scene.traverse(obj => {
        if (obj instanceof THREE.Mesh) obj.geometry.dispose()
        if (obj instanceof THREE.Sprite) { obj.material.map?.dispose(); obj.material.dispose() }
      }))
      renderer?.dispose()
    },
  }
}
