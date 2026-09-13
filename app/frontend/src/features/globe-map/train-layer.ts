import * as THREE from 'three'
import { MercatorCoordinate, type CustomLayerInterface, type Map } from 'maplibre-gl'
import type { Journey, Prediction } from '@/lib/contract'
import { motionOff } from '@/lib/motion'
import { riskColour } from '@/lib/geo'

// Exaggerated miniature trains, not live vehicle positions. Uses the map's own
// globe/mercator projection so models stay attached during the camera flight.
export function createTrainLayer(journey: Journey, prediction?: Prediction): CustomLayerInterface {
  let renderer: THREE.WebGLRenderer
  let map: Map
  const camera = new THREE.Camera()
  const assets: { scene: THREE.Scene; line: [number, number][]; pillar: boolean }[] = []
  const box = (group: THREE.Group, size: [number, number, number], position: [number, number, number], color: string) => {
    const mesh = new THREE.Mesh(new THREE.BoxGeometry(...size), new THREE.MeshStandardMaterial({ color, roughness: .45 }))
    mesh.position.set(...position); group.add(mesh)
  }
  const sceneFor = (group: THREE.Group) => {
    const scene = new THREE.Scene()
    scene.add(new THREE.AmbientLight(0xffffff, 2))
    const light = new THREE.DirectionalLight(0xffffff, 3); light.position.set(2, 5, 4); scene.add(light, group)
    return scene
  }
  journey.legs.forEach((leg, i) => {
    if (!leg.routeGeometry?.length) return
    const train = new THREE.Group()
    const regional = /^(RB|RE|S\s)/.test(leg.trainId)
    for (let car = 0; car < 3; car++) {
      const z = car * 3.4
      box(train, [1.1, .9, 3.1], [0, .8, z], regional ? '#c84438' : '#f8faf7')
      box(train, [1.13, .12, 3.05], [0, .6, z], '#d83a32')
      box(train, [1.15, .27, 2.35], [0, .98, z], '#233e47')
      box(train, [.85, .25, 2.6], [0, .2, z], '#28312d')
    }
    assets.push({ scene: sceneFor(train), line: leg.routeGeometry, pillar: false })
    const delay = prediction?.legs[i]?.expectedDelayMinutes.value
    if (delay != null) {
      const pillar = new THREE.Group()
      const height = .4 + Math.min(30, Math.max(0, delay)) / 3
      box(pillar, [.8, height, .8], [0, height / 2, 0], riskColour(Math.min(1, delay / 30)))
      assets.push({ scene: sceneFor(pillar), line: [leg.routeGeometry.at(-1)!], pillar: true })
    }
  })
  return {
    id: 'journey-miniatures', type: 'custom', renderingMode: '3d',
    onAdd(m, gl) {
      map = m
      renderer = new THREE.WebGLRenderer({ canvas: m.getCanvas(), context: gl as WebGL2RenderingContext, antialias: true })
      renderer.autoClear = false
    },
    render(_gl, args) {
      const moving = !motionOff() && !document.hidden
      const t = moving ? (performance.now() % 24000) / 24000 : .35
      for (const asset of assets) {
        const position = t * (asset.line.length - 1)
        const index = Math.min(Math.floor(position), Math.max(0, asset.line.length - 2))
        const a = asset.line[index], b = asset.line[Math.min(index + 1, asset.line.length - 1)]
        const fraction = position - index
        const lon = a[0] + (b[0] - a[0]) * fraction, lat = a[1] + (b[1] - a[1]) * fraction
        const globe = args.defaultProjectionData.projectionTransition > 0
        let model: THREE.Matrix4
        if (globe) {
          model = new THREE.Matrix4().makeRotationY(lon * Math.PI / 180)
            .multiply(new THREE.Matrix4().makeRotationX(-lat * Math.PI / 180))
            .multiply(new THREE.Matrix4().makeTranslation(0, 0, 1.00001))
            .multiply(new THREE.Matrix4().makeRotationX(Math.PI / 2))
            .scale(new THREE.Vector3(1 / 6371008.8, 1 / 6371008.8, 1 / 6371008.8))
        } else {
          const merc = MercatorCoordinate.fromLngLat([lon, lat], 15)
          const scale = merc.meterInMercatorCoordinateUnits()
          model = new THREE.Matrix4().makeTranslation(merc.x, merc.y, merc.z)
            .multiply(new THREE.Matrix4().makeRotationZ(Math.PI))
            .multiply(new THREE.Matrix4().makeRotationX(Math.PI / 2))
            .scale(new THREE.Vector3(-scale, scale, scale))
        }
        // Keep the miniature legible as the camera changes scale.
        const scale = Math.max(18, Math.min(2200, 1800 / 2 ** (map.getZoom() - 6)))
        model.scale(new THREE.Vector3(scale, scale, scale))
        if (!asset.pillar) model.multiply(new THREE.Matrix4().makeRotationY(Math.atan2((b[0] - a[0]) * Math.cos(lat * Math.PI / 180), b[1] - a[1])))
        camera.projectionMatrix.fromArray(args.defaultProjectionData.mainMatrix).multiply(model)
        renderer.resetState(); renderer.render(asset.scene, camera)
      }
      if (moving && assets.length) map.triggerRepaint()
    },
    onRemove() {
      assets.forEach(({ scene }) => scene.traverse(obj => {
        if (obj instanceof THREE.Mesh) { obj.geometry.dispose(); (Array.isArray(obj.material) ? obj.material : [obj.material]).forEach(m => m.dispose()) }
      }))
      renderer?.dispose()
    },
  }
}
