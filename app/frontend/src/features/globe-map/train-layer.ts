import * as THREE from 'three'
import { MercatorCoordinate, type CustomLayerInterface, type Map } from 'maplibre-gl'
import type { Journey, Prediction } from '@/lib/contract'
import { motionOff } from '@/lib/motion'
import { trainVisual } from '@/lib/train-service'
import { buildTrack, sampleTrack, validTrack } from '@/lib/track-path'

// Exaggerated miniature trains, not live vehicle positions. Uses the map's own
// globe/mercator projection so models stay attached during the camera flight.
export function createTrainLayer(journey: Journey, _prediction?: Prediction): CustomLayerInterface {
  let renderer: THREE.WebGLRenderer
  let map: Map
  const camera = new THREE.Camera()
  const assets: { scene: THREE.Scene; track: ReturnType<typeof buildTrack>; car: number }[] = []
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
  journey.legs.forEach(leg => {
    if (!validTrack(leg.routeGeometry)) return
    const track = buildTrack(leg.routeGeometry)
    const style = trainVisual(leg)
    for (let car = 0; car < 3; car++) {
      const train = new THREE.Group()
      box(train, [1.1, .85, 2.7], [0, .75, 0], style.color)
      box(train, [1.12, .12, 2.7], [0, .52, 0], style.kind === 'unknown' ? '#415951' : '#d73c34')
      box(train, [1.13, .28, 2.25], [0, .9, 0], '#233e47')
      box(train, [.85, .22, 2.3], [0, .2, 0], '#28312d')
      for (let door = 0; door < style.doors; door++) {
        const z = style.doors === 1 ? -.95 : -.95 + door * 1.9 / (style.doors - 1)
        box(train, [1.15, .65, .23], [0, .73, z], style.kind === 'sbahn' ? '#edd8a0' : '#bac5c3')
      }
      if (car === 0) {
        // Category silhouette, not a claim about the operator's exact fleet.
        const nose = new THREE.Mesh(new THREE.SphereGeometry(1, 16, 12), new THREE.MeshStandardMaterial({ color: style.color, roughness: .45 }))
        nose.scale.set(.55, .42, style.nose); nose.position.set(0, .73, 1.25); train.add(nose)
        box(train, [.78, .22, .12], [0, .96, 1.35 + style.nose * .6], '#233e47')
        box(train, [.65, .07, .12], [0, .58, 1.35 + style.nose * .8], '#fff2bb')
      }
      assets.push({ scene: sceneFor(train), track, car })
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
        // Each carriage has its own track anchor and tangent, including at bends.
        const scale = Math.min(asset.track.length / 30, Math.max(18, Math.min(2200, 1800 / 2 ** (map.getZoom() - 6))))
        const distance = t * asset.track.length - asset.car * 3.5 * scale
        if (distance < 0) continue
        const { point: [lon, lat], heading } = sampleTrack(asset.track, distance)
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
        model.scale(new THREE.Vector3(scale, scale, scale))
        model.multiply(new THREE.Matrix4().makeRotationY(heading))
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
