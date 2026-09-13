import * as THREE from 'three'
import type { TrainKind, TrainVisual } from '@/lib/train-service'

// Procedural miniature rolling stock. Category silhouettes (streamlined white
// ICE, red regional stock, red-and-white S-Bahn), not a claim about the exact
// fleet on the day. Local axes: +Z is the direction of travel, Y up, rail at y=0.
export const CAR_LENGTH = 3.6
export const CAR_GAP = .28
export const CAR_PITCH = CAR_LENGTH + CAR_GAP
const W = 1

export function carCount(kind: TrainKind) {
  return { ice: 5, intercity: 4, re: 4, rb: 3, sbahn: 3, unknown: 3 }[kind]
}

const materials = new Map<string, THREE.MeshStandardMaterial>()
const paint = (color: string, roughness = .38, metalness = .12, emissive?: string) => {
  const key = `${color}/${roughness}/${metalness}/${emissive ?? ''}`
  let m = materials.get(key)
  if (!m) { m = new THREE.MeshStandardMaterial({ color, roughness, metalness, ...(emissive ? { emissive, emissiveIntensity: 1.4 } : {}) }); materials.set(key, m) }
  return m
}
const glass = () => paint('#16242c', .18, .75)
const dark = () => paint('#1f2628', .7, .2)
const steel = () => paint('#7e868a', .5, .6)

function box(group: THREE.Group, size: [number, number, number], at: [number, number, number], material: THREE.Material) {
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(...size), material)
  mesh.position.set(...at); group.add(mesh); return mesh
}

function bogie(group: THREE.Group, z: number) {
  box(group, [.72, .16, .78], [0, .3, z], dark())
  for (const x of [-.44, .44]) for (const dz of [-.24, .24]) {
    const wheel = new THREE.Mesh(new THREE.CylinderGeometry(.16, .16, .07, 18), steel())
    wheel.rotation.z = Math.PI / 2; wheel.position.set(x, .16, z + dz); group.add(wheel)
  }
}

function nose(group: THREE.Group, style: TrainVisual, direction: 1 | -1, body: THREE.Material) {
  const L = CAR_LENGTH
  const reach = style.nose * 1.15
  const cone = new THREE.Mesh(new THREE.SphereGeometry(.5, 22, 14), body)
  cone.scale.set(W, .74, reach * 2); cone.position.set(0, .88, direction * (L / 2 - .05)); group.add(cone)
  const screen = box(group, [.68, .3, .08], [0, 1.06, direction * (L / 2 + reach * .38)], glass())
  screen.rotation.x = direction * -.55
  for (const x of [-.27, .27]) {
    const lamp = new THREE.Mesh(new THREE.SphereGeometry(.06, 10, 8), direction === 1 ? paint('#fff7d6', .3, 0, '#fff1b0') : paint('#ff5a4d', .3, 0, '#ff2d1f'))
    lamp.position.set(x, .72, direction * (L / 2 + reach * .92)); group.add(lamp)
  }
}

export function buildCar(style: TrainVisual, index: number, count: number): THREE.Group {
  const car = new THREE.Group()
  const L = CAR_LENGTH
  const body = paint(style.color, style.kind === 'ice' || style.kind === 'intercity' ? .32 : .42, .14)
  const accent = style.kind === 'ice' || style.kind === 'intercity' ? paint('#d7302a', .4, .1) : paint('#f1f1ec', .45, .05)
  // Shadow keeps the miniature grounded on the imagery.
  const shadow = new THREE.Mesh(new THREE.PlaneGeometry(W * 1.7, L * 1.08), new THREE.MeshBasicMaterial({ color: '#000000', transparent: true, opacity: .26, depthWrite: false }))
  shadow.rotation.x = -Math.PI / 2; shadow.position.y = .01; car.add(shadow)
  box(car, [.84, .16, L - .2], [0, .42, 0], dark())
  bogie(car, L / 2 - .78); bogie(car, -(L / 2 - .78))
  box(car, [W, .72, L], [0, .88, 0], body)
  const roof = new THREE.Mesh(new THREE.CylinderGeometry(W / 2, W / 2, L - .06, 18, 1, false), body)
  roof.rotation.x = Math.PI / 2; roof.scale.y = 1; roof.scale.x = 1; roof.scale.z = 1
  roof.scale.set(1, 1, .36); roof.rotation.set(Math.PI / 2, 0, 0); roof.position.set(0, 1.24, 0); car.add(roof)
  box(car, [W + .02, .25, L - .5], [0, 1.0, 0], glass())
  box(car, [W + .03, .08, L], [0, .79, 0], accent)
  const doors = style.kind === 'sbahn' ? 3 : style.kind === 'ice' ? 1 : 2
  for (let d = 0; d < doors; d++) {
    const z = doors === 1 ? L / 2 - .5 : -L / 2 + .55 + d * (L - 1.1) / (doors - 1)
    box(car, [W + .03, .6, .24], [0, .84, z], style.kind === 'sbahn' ? paint('#efe0b6', .5, 0) : paint(style.kind === 'ice' ? '#dfe3e0' : '#efe3df', .5, .05))
  }
  box(car, [.46, .1, .9], [0, 1.44, .3], steel())
  if (count > 1 && index === 1) {
    for (const z of [-.28, .28]) box(car, [.05, .34, .05], [0, 1.62, z], dark())
    box(car, [.66, .03, .08], [0, 1.8, 0], steel())
  }
  if (index === 0) nose(car, style, 1, body)
  if (index === count - 1 && (index > 0 || style.kind !== 'sbahn')) nose(car, style, -1, body)
  return car
}

export function buildLabel(text: string, color: string, y: number): THREE.Sprite {
  const canvas = document.createElement('canvas'); canvas.width = 768; canvas.height = 112
  const ctx = canvas.getContext('2d')!
  ctx.fillStyle = color; ctx.beginPath(); ctx.roundRect(0, 0, 768, 112, 40); ctx.fill()
  ctx.strokeStyle = '#ffffff55'; ctx.lineWidth = 4; ctx.stroke()
  ctx.fillStyle = '#ffffff'; ctx.font = '600 36px system-ui, sans-serif'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'
  ctx.fillText(text, 384, 58, 720)
  const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: new THREE.CanvasTexture(canvas), depthTest: false, transparent: true }))
  sprite.scale.set(6.4, .93, 1); sprite.position.set(0, y, 0)
  return sprite
}

export function sceneWith(group: THREE.Object3D): THREE.Scene {
  const scene = new THREE.Scene()
  scene.add(new THREE.HemisphereLight('#e8f0f8', '#4f5c4a', 1.7))
  scene.add(new THREE.AmbientLight('#ffffff', .7))
  const sun = new THREE.DirectionalLight('#fff4e0', 2.4); sun.position.set(2.5, 6, 3)
  const fill = new THREE.DirectionalLight('#c9dcff', .8); fill.position.set(-3, 2, -2)
  scene.add(sun, fill, group)
  return scene
}
