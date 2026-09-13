import * as THREE from 'three'
import { MercatorCoordinate, type CustomLayerInterface, type Map } from 'maplibre-gl'
import type { Journey, Prediction } from '@/lib/contract'
import { trainDelay, trainScale, storyProgress, disruptionKind } from '@/lib/train-story'
import { motionOff } from '@/lib/motion'
import { trainVisual } from '@/lib/train-service'
import { buildTrack, sampleTrack, validTrack } from '@/lib/track-path'

// Exaggerated miniature trains, not live vehicle positions. Uses the map's own
// globe/mercator projection so models stay attached during the camera flight.
export function createTrainLayer(journey: Journey, prediction?: Prediction): CustomLayerInterface {
  let renderer: THREE.WebGLRenderer
  let map: Map
  const camera = new THREE.Camera()
  const assets: { scene: THREE.Scene; track: ReturnType<typeof buildTrack>; car: number; delay?: number; fixed?: boolean }[] = []
  let elapsed = 45000, lastFrame: number | undefined
  const resume = () => { lastFrame = undefined; if (!document.hidden) map?.triggerRepaint() }
  const label = (group: THREE.Group, text: string, color: string, y = 2.6) => {
    const canvas = document.createElement('canvas'); canvas.width = 768; canvas.height = 112
    const ctx = canvas.getContext('2d')!
    ctx.fillStyle = color; ctx.beginPath(); ctx.roundRect(0, 0, 768, 112, 22); ctx.fill()
    ctx.fillStyle = '#ffffff'; ctx.font = 'bold 34px sans-serif'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'
    ctx.fillText(text, 384, 56, 730)
    const texture = new THREE.CanvasTexture(canvas)
    const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: texture, depthTest: false }))
    sprite.scale.set(8, 1.17, 1); sprite.position.set(0, y, 0); group.add(sprite)
  }
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
  journey.legs.forEach((leg, index) => {
    if (!validTrack(leg.routeGeometry)) return
    const track = buildTrack(leg.routeGeometry)
    const style = trainVisual(leg)
    const delay = trainDelay(journey, leg, index, prediction)
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
      if (car === 0) {
        label(train, `${leg.trainId} · ${delay == null ? 'No delay estimate' : `+${Math.round(delay)} min estimated`}`, delay && delay > 5 ? '#aa4f19' : '#285548')
        if (delay != null && delay > 0) {
          const ring = new THREE.Mesh(new THREE.TorusGeometry(.9, .09, 8, 32), new THREE.MeshBasicMaterial({ color: '#f7a629', transparent: true, opacity: .85 }))
          ring.rotation.x = Math.PI / 2; ring.position.y = .12; train.add(ring)
        }
      }
      assets.push({ scene: sceneFor(train), track, car, delay })
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
      label(obstacle, `${leg.trainId} · ${kind === 'reported' ? 'Service notice' : `Reported ${kind}`}`, '#794723')
      label(obstacle, 'Illustrative location · see notice', '#42594f', 3.8)
      assets.push({ scene: sceneFor(obstacle), track, car: 0, fixed: true })
    }
  })
  return {
    id: 'journey-miniatures', type: 'custom', renderingMode: '3d',
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
      for (const asset of assets) {
        // Each carriage has its own track anchor and tangent, including at bends.
        const scale = trainScale(map.getZoom(), asset.track.length)
        const t = asset.fixed ? .7 : storyProgress(elapsed, asset.delay)
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
        // Local +Z points south in the map transform; convert compass heading.
        model.multiply(new THREE.Matrix4().makeRotationY(Math.PI - heading))
        camera.projectionMatrix.fromArray(args.defaultProjectionData.mainMatrix).multiply(model)
        renderer.resetState(); renderer.render(asset.scene, camera)
      }
      if (moving && assets.length) map.triggerRepaint()
    },
    onRemove() {
      document.removeEventListener("visibilitychange", resume)
      assets.forEach(({ scene }) => scene.traverse(obj => {
        if (obj instanceof THREE.Mesh || obj instanceof THREE.Sprite) {
          if (obj instanceof THREE.Mesh) obj.geometry.dispose()
          ;(Array.isArray(obj.material) ? obj.material : [obj.material]).forEach(m => { if ('map' in m) (m.map as THREE.Texture | null)?.dispose(); m.dispose() })
        }
      }))
      renderer?.dispose()
    },
  }
}
