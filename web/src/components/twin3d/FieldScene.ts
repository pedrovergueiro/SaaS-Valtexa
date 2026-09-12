/**
 * O motor da cópia 3D do talhão — three.js puro, fora do React.
 *
 * A página cria uma instância, entrega a cena que a API devolveu e conversa
 * com ela por métodos (`setData`, `setColorMode`, `view`...). O React fica com
 * o que é interface; aqui fica o que é GPU. Misturar os dois faria cada
 * atualização de estado da tela reconstruir dezenas de milhares de plantas.
 *
 * Coordenadas: a API fala no plano do talhão em metros (x leste, y norte, z
 * para cima). O three.js usa y para cima, então (x, y, z) vira (x, z, −y) — o
 * norte fica para o fundo da tela na vista inicial.
 *
 * Renderiza sob demanda: só desenha quando a câmera mexe ou algo muda. Um
 * talhão inteiro redesenhado a 60 quadros por segundo esquentaria o notebook
 * de quem só está olhando.
 */
import * as THREE from 'three'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'
import { CSS2DObject, CSS2DRenderer } from 'three/addons/renderers/CSS2DRenderer.js'

import type { FieldSceneOut, SceneMarkerOut } from '@/api/types'
import type { PointCloud } from '@/lib/ply'

import { geometryForCrop } from './plantGeometry'

export type Category = 'disease' | 'pest' | 'review' | 'other' | 'healthy'
export type ColorMode = 'appearance' | 'height' | 'age'
export type ViewName = 'overview' | 'top'

export const MARKER_CATEGORIES: Category[] = ['pest', 'disease', 'review', 'other', 'healthy']

export type SceneTheme = {
  dark: boolean
  horizon: string
  ground: string
  soil: string
  soilScanned: string
  border: string
  zone: string
  accent: string
  categories: Record<Category, string>
  leaf: [healthy: string, tired: string]
  heightRamp: [low: string, mid: string, high: string]
  ageRamp: [fresh: string, old: string]
}

export type Hover =
  | { kind: 'marker'; marker: SceneMarkerOut; x: number; y: number }
  | { kind: 'plant'; index: number; x: number; y: number }
  | null

type Handlers = {
  onHover?: (hover: Hover) => void
  onSelectMarker?: (marker: SceneMarkerOut) => void
  onSelectPlant?: (index: number) => void
}

type Tween = {
  from: { position: THREE.Vector3; target: THREE.Vector3 }
  to: { position: THREE.Vector3; target: THREE.Vector3 }
  start: number
  duration: number
}

const MARKER_LIFT = 0.8
const MARKER_PX: Record<Category, number> = { pest: 18, disease: 16, review: 13, other: 12, healthy: 7 }
const PICK_PX = 16

/** Plano do talhão → mundo do three.js. */
const world = (x: number, y: number, z = 0) => new THREE.Vector3(x, z, -y)

const ease = (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2)

export class FieldScene {
  private readonly renderer: THREE.WebGLRenderer
  private readonly labels: CSS2DRenderer
  private readonly scene = new THREE.Scene()
  private readonly camera = new THREE.PerspectiveCamera(42, 1, 0.1, 6000)
  private readonly controls: OrbitControls
  private readonly hemisphere = new THREE.HemisphereLight('#ffffff', '#444444', 1.15)
  private readonly sun = new THREE.DirectionalLight('#fff4e0', 1.7)
  private readonly content = new THREE.Group()
  private readonly clouds = new THREE.Group()
  private readonly resize: ResizeObserver
  private readonly handlers: Handlers

  private theme: SceneTheme
  private data: FieldSceneOut | null = null
  private mode: ColorMode = 'appearance'
  private visible = new Set<Category>(['pest', 'disease', 'review', 'other'])
  private plants: THREE.InstancedMesh | null = null
  private markerLayers: { category: Category; points: THREE.Points; markers: SceneMarkerOut[] }[] = []
  private halo: THREE.Points | null = null
  private cloudScans = new Set<string>()
  private plantGrid = new Map<string, number[]>()
  private textures = new Map<string, THREE.Texture>()
  private extent = 100
  private center = new THREE.Vector3()
  private framed = 100
  private laneDirection = new THREE.Vector3(1, 0, 0)
  private dirty = true
  private tween: Tween | null = null
  private down: { x: number; y: number } | null = null
  private hovered: SceneMarkerOut | null = null
  private pendingMove: PointerEvent | null = null

  constructor(
    private readonly container: HTMLElement,
    theme: SceneTheme,
    handlers: Handlers = {},
  ) {
    this.theme = theme
    this.handlers = handlers

    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'high-performance' })
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    this.renderer.outputColorSpace = THREE.SRGBColorSpace
    this.renderer.domElement.style.display = 'block'
    this.renderer.domElement.style.touchAction = 'none'
    container.appendChild(this.renderer.domElement)

    this.labels = new CSS2DRenderer()
    Object.assign(this.labels.domElement.style, { position: 'absolute', inset: '0', pointerEvents: 'none' })
    container.appendChild(this.labels.domElement)

    this.controls = new OrbitControls(this.camera, this.renderer.domElement)
    this.controls.enableDamping = true
    this.controls.dampingFactor = 0.09
    this.controls.maxPolarAngle = Math.PI * 0.485
    this.controls.minDistance = 1.2
    this.controls.screenSpacePanning = false
    this.controls.addEventListener('start', () => {
      this.tween = null
    })

    this.sun.position.set(-120, 180, 90)
    this.scene.add(this.hemisphere, this.sun, this.content, this.clouds)

    const canvas = this.renderer.domElement
    canvas.addEventListener('pointerdown', this.onPointerDown)
    canvas.addEventListener('pointermove', this.onPointerMove)
    canvas.addEventListener('pointerup', this.onPointerUp)
    canvas.addEventListener('pointerleave', this.onPointerLeave)

    this.resize = new ResizeObserver(() => this.fit())
    this.resize.observe(container)
    this.fit()
    this.setTheme(theme)
    this.renderer.setAnimationLoop(this.frame)
  }

  // --- API -----------------------------------------------------------------

  setData(data: FieldSceneOut) {
    const first = this.data === null
    this.data = data
    this.rebuild()
    if (first) this.view('overview', false)
  }

  setTheme(theme: SceneTheme) {
    this.theme = theme
    this.hemisphere.color.set(theme.dark ? '#9fb3c8' : '#ffffff')
    this.hemisphere.groundColor.set(theme.dark ? '#1c2420' : '#6b5d4b')
    this.hemisphere.intensity = theme.dark ? 0.9 : 1.15
    this.sun.intensity = theme.dark ? 1.1 : 1.7
    for (const texture of this.textures.values()) texture.dispose()
    this.textures.clear()
    if (this.data) this.rebuild()
    this.dirty = true
  }

  setColorMode(mode: ColorMode) {
    this.mode = mode
    this.paintPlants()
  }

  setVisible(categories: Set<Category>) {
    this.visible = new Set(categories)
    this.buildMarkers()
    this.paintPlants()
  }

  /** Vistas prontas: o talhão inteiro de lado, ou de cima como um mapa. */
  view(name: ViewName, animate = true) {
    const size = this.framed * 1.25
    const target = this.center.clone()
    const position =
      name === 'top'
        ? new THREE.Vector3(target.x, size * 1.15, target.z + 0.01)
        : new THREE.Vector3(target.x + size * 0.32, size * 0.52, target.z + size * 0.78)
    this.moveCamera(position, target, animate)
  }

  /** Coloca a câmera dentro da rua, na altura do sensor do rover, olhando ao longo dela. */
  walkLane(index: number) {
    const scan = this.data?.scans[index]
    if (!scan || scan.path.length < 2) return
    const [sx, sy] = scan.path[0] as [number, number]
    const [ex, ey] = scan.path[scan.path.length - 1] as [number, number]
    const start = world(sx, sy)
    const end = world(ex, ey)
    const direction = end.clone().sub(start).normalize()
    const eye = start.clone().addScaledVector(direction, -2).setY(1.35)
    const target = start.clone().addScaledVector(direction, 9).setY(0.7)
    this.moveCamera(eye, target, true)
  }

  focusMarker(marker: SceneMarkerOut) {
    const target = world(marker.x, marker.y, marker.z)
    const side = new THREE.Vector3(-this.laneDirection.z, 0, this.laneDirection.x)
    const position = target.clone().addScaledVector(side, 3.2).addScaledVector(this.laneDirection, -2.4).setY(target.y + 2.6)
    this.moveCamera(position, target, true)
  }

  focusPlant(index: number) {
    const plants = this.data?.plants
    if (!plants) return
    const height = plants.height[index] ?? 1
    const target = world(plants.x[index] ?? 0, plants.y[index] ?? 0, height * 0.6)
    const side = new THREE.Vector3(-this.laneDirection.z, 0, this.laneDirection.x)
    this.moveCamera(target.clone().addScaledVector(side, 2.2).setY(height + 1.4), target, true)
  }

  /** Mostra a nuvem de pontos real de uma rua no lugar das plantas desenhadas. */
  showCloud(scanId: string, cloud: PointCloud) {
    const scan = this.data?.scans.find((item) => item.id === scanId)
    if (!scan) return
    this.hideCloud(scanId)
    const [ox, oy] = scan.origin as [number, number]
    const positions = new Float32Array(cloud.count * 3)
    const colors = new Float32Array(cloud.count * 3)
    const linear = srgbTable()
    for (let index = 0; index < cloud.count; index += 1) {
      const x = cloud.positions[index * 3]! + ox
      const y = cloud.positions[index * 3 + 1]! + oy
      positions[index * 3] = x
      positions[index * 3 + 1] = cloud.positions[index * 3 + 2]!
      positions[index * 3 + 2] = -y
      colors[index * 3] = linear[cloud.colors[index * 3]!]!
      colors[index * 3 + 1] = linear[cloud.colors[index * 3 + 1]!]!
      colors[index * 3 + 2] = linear[cloud.colors[index * 3 + 2]!]!
    }
    const geometry = new THREE.BufferGeometry()
    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3))
    geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3))
    geometry.computeBoundingSphere()
    const points = new THREE.Points(
      geometry,
      new THREE.PointsMaterial({ size: 0.06, vertexColors: true, sizeAttenuation: true }),
    )
    points.userData.scanId = scanId
    this.clouds.add(points)
    this.cloudScans.add(scanId)
    this.placePlants()
  }

  hideCloud(scanId: string) {
    for (const child of [...this.clouds.children]) {
      if (child.userData.scanId !== scanId) continue
      this.clouds.remove(child)
      disposeObject(child)
    }
    if (this.cloudScans.delete(scanId)) this.placePlants()
  }

  hasCloud(scanId: string) {
    return this.cloudScans.has(scanId)
  }

  dispose() {
    this.renderer.setAnimationLoop(null)
    this.resize.disconnect()
    const canvas = this.renderer.domElement
    canvas.removeEventListener('pointerdown', this.onPointerDown)
    canvas.removeEventListener('pointermove', this.onPointerMove)
    canvas.removeEventListener('pointerup', this.onPointerUp)
    canvas.removeEventListener('pointerleave', this.onPointerLeave)
    this.controls.dispose()
    disposeObject(this.scene)
    for (const texture of this.textures.values()) texture.dispose()
    this.renderer.dispose()
    canvas.remove()
    this.labels.domElement.remove()
  }

  // --- construção ------------------------------------------------------------

  private rebuild() {
    const data = this.data
    if (!data) return
    for (const child of [...this.content.children]) {
      this.content.remove(child)
      disposeObject(child)
    }
    this.plants = null
    this.markerLayers = []
    this.halo = null

    const xs = data.boundary.map((point) => point[0] ?? 0)
    const ys = data.boundary.map((point) => point[1] ?? 0)
    const [minX, maxX, minY, maxY] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)]
    this.extent = Math.max(40, maxX - minX, maxY - minY)
    this.center = world((minX + maxX) / 2, (minY + maxY) / 2)
    this.framed = this.extent
    const scanned = scannedBox(data)
    if (scanned) {
      this.center = world((scanned[0] + scanned[1]) / 2, (scanned[2] + scanned[3]) / 2)
      this.framed = Math.max(25, scanned[1] - scanned[0], scanned[3] - scanned[2])
    }
    this.scene.fog = new THREE.Fog(this.theme.horizon, this.extent * 1.1, this.extent * 3.2)
    this.controls.maxDistance = this.extent * 3

    const lane = data.scans[0]?.path
    if (lane && lane.length > 1) {
      const a = world(lane[0]![0]!, lane[0]![1]!)
      const b = world(lane[lane.length - 1]![0]!, lane[lane.length - 1]![1]!)
      if (a.distanceTo(b) > 0) this.laneDirection = b.sub(a).normalize()
    }

    this.buildGround(data)
    this.buildPlants(data)
    this.buildMarkers()
    this.buildDevices(data)
    this.buildPendingLanes(data)
    for (const child of [...this.clouds.children]) {
      if (!data.scans.some((scan) => scan.id === child.userData.scanId)) {
        this.cloudScans.delete(child.userData.scanId as string)
        this.clouds.remove(child)
        disposeObject(child)
      }
    }
    this.placePlants()
    this.dirty = true
  }

  private buildGround(data: FieldSceneOut) {
    const theme = this.theme
    const outside = new THREE.Mesh(
      new THREE.PlaneGeometry(this.extent * 8, this.extent * 8).rotateX(-Math.PI / 2),
      new THREE.MeshLambertMaterial({ color: theme.ground }),
    )
    outside.position.set(this.center.x, -0.03, this.center.z)
    this.content.add(outside)

    const shape = new THREE.Shape(data.boundary.map(([x = 0, y = 0]) => new THREE.Vector2(x, y)))
    const field = new THREE.Mesh(
      new THREE.ShapeGeometry(shape).rotateX(-Math.PI / 2),
      new THREE.MeshLambertMaterial({ color: theme.soil }),
    )
    this.content.add(field)

    // O chão por onde o rover já passou fica mais escuro: é a parte do
    // talhão que tem cópia. O resto, claro e vazio, é o que ninguém mediu.
    const strips: number[] = []
    for (const scan of data.scans) {
      for (let index = 0; index < scan.path.length - 1; index += 1) {
        const [ax = 0, ay = 0] = scan.path[index]!
        const [bx = 0, by = 0] = scan.path[index + 1]!
        const length = Math.hypot(bx - ax, by - ay)
        if (!length) continue
        const nx = (-(by - ay) / length) * scan.reach_m
        const ny = ((bx - ax) / length) * scan.reach_m
        const corners = [
          [ax + nx, ay + ny],
          [bx + nx, by + ny],
          [bx - nx, by - ny],
          [ax - nx, ay - ny],
        ] as const
        for (const corner of [0, 1, 2, 0, 2, 3]) {
          const [x, y] = corners[corner]!
          strips.push(x, 0.004, -y)
        }
      }
    }
    if (strips.length) {
      const geometry = new THREE.BufferGeometry()
      geometry.setAttribute('position', new THREE.Float32BufferAttribute(strips, 3))
      geometry.computeVertexNormals()
      this.content.add(
        new THREE.Mesh(
          geometry,
          new THREE.MeshLambertMaterial({ color: theme.soilScanned, side: THREE.DoubleSide }),
        ),
      )
    }

    const border = new THREE.LineLoop(
      new THREE.BufferGeometry().setFromPoints(data.boundary.map(([x = 0, y = 0]) => world(x, y, 0.05))),
      new THREE.LineBasicMaterial({ color: theme.border }),
    )
    this.content.add(border)

    for (const zone of data.zones) {
      const outline = new THREE.LineLoop(
        new THREE.BufferGeometry().setFromPoints(zone.boundary.map(([x = 0, y = 0]) => world(x, y, 0.07))),
        new THREE.LineDashedMaterial({ color: theme.zone, dashSize: 2.2, gapSize: 1.4 }),
      )
      outline.computeLineDistances()
      this.content.add(outline)
      const [x = 0, y = 0] = zone.boundary.reduce(
        (acc, point) => [Math.max(acc[0]!, point[0] ?? -Infinity), Math.max(acc[1]!, point[1] ?? -Infinity)],
        [-Infinity, -Infinity],
      )
      this.content.add(label(`${zone.name}`, 'zone', world(x, y, 0.1)))
    }
  }

  private buildPlants(data: FieldSceneOut) {
    const { plants } = data
    const count = plants.x.length
    this.plantGrid.clear()
    for (let index = 0; index < count; index += 1) {
      const key = `${Math.floor(plants.x[index]!)}:${Math.floor(plants.y[index]!)}`
      const bucket = this.plantGrid.get(key)
      if (bucket) bucket.push(index)
      else this.plantGrid.set(key, [index])
    }
    if (!count) return

    const mesh = new THREE.InstancedMesh(
      geometryForCrop(data.crop),
      new THREE.MeshLambertMaterial({ vertexColors: true, side: THREE.DoubleSide }),
      count,
    )
    mesh.instanceMatrix.setUsage(THREE.StaticDrawUsage)
    this.plants = mesh
    this.content.add(mesh)
    this.paintPlants()
  }

  /** Posição e tamanho de cada planta; as de rua com nuvem aberta somem. */
  private placePlants() {
    const mesh = this.plants
    const data = this.data
    if (!mesh || !data) return
    const hidden = new Set(
      data.scans.flatMap((scan, index) => (this.cloudScans.has(scan.id) ? [index] : [])),
    )
    const matrix = new THREE.Matrix4()
    const rotation = new THREE.Quaternion()
    const up = new THREE.Vector3(0, 1, 0)
    const position = new THREE.Vector3()
    const scale = new THREE.Vector3()
    const { x, y, height, canopy, scan } = data.plants
    for (let index = 0; index < x.length; index += 1) {
      const px = x[index]!
      const py = y[index]!
      position.set(px, 0, -py)
      rotation.setFromAxisAngle(up, hash(px, py) * Math.PI * 2)
      if (hidden.has(scan[index]!)) scale.set(0, 0, 0)
      else scale.set(canopy[index]!, height[index]!, canopy[index]!)
      mesh.setMatrixAt(index, matrix.compose(position, rotation, scale))
    }
    mesh.instanceMatrix.needsUpdate = true
    mesh.computeBoundingSphere()
    this.dirty = true
  }

  /** A cor de cada planta, pelo modo escolhido — e a da planta diagnosticada por cima. */
  private paintPlants() {
    const mesh = this.plants
    const data = this.data
    if (!mesh || !data) return
    const { height, greenness, scan } = data.plants
    const theme = this.theme
    const color = new THREE.Color()
    const healthy = new THREE.Color(theme.leaf[0])
    const tired = new THREE.Color(theme.leaf[1])
    const ramp = theme.heightRamp.map((value) => new THREE.Color(value))
    const fresh = new THREE.Color(theme.ageRamp[0])
    const old = new THREE.Color(theme.ageRamp[1])

    const sorted = [...height].sort((a, b) => a - b)
    const low = sorted[Math.floor(sorted.length * 0.05)] ?? 0
    const high = sorted[Math.floor(sorted.length * 0.95)] ?? 1
    const at = new Date(data.at).getTime()
    const ages = data.scans.map((item) => (at - new Date(item.captured_at).getTime()) / 86_400_000)
    const oldest = Math.max(7, ...ages)

    for (let index = 0; index < height.length; index += 1) {
      if (this.mode === 'height') {
        const t = clamp01((height[index]! - low) / Math.max(0.01, high - low))
        if (t < 0.5) color.copy(ramp[0]!).lerp(ramp[1]!, t * 2)
        else color.copy(ramp[1]!).lerp(ramp[2]!, (t - 0.5) * 2)
      } else if (this.mode === 'age') {
        color.copy(fresh).lerp(old, clamp01((ages[scan[index]!] ?? 0) / oldest))
      } else {
        const green = greenness[index] ?? 0.78
        color.copy(healthy).lerp(tired, clamp01((0.8 - green) / 0.45))
      }
      mesh.setColorAt(index, color)
    }

    for (const marker of data.markers) {
      const category = marker.category as Category
      if (marker.plant == null || category === 'healthy' || !this.visible.has(category)) continue
      mesh.getColorAt(marker.plant, color)
      mesh.setColorAt(marker.plant, color.lerp(new THREE.Color(theme.categories[category]), 0.85))
    }
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true
    this.dirty = true
  }

  private buildMarkers() {
    for (const layer of this.markerLayers) {
      this.content.remove(layer.points)
      disposeObject(layer.points)
    }
    this.markerLayers = []
    const data = this.data
    if (!data) return

    const stems: number[] = []
    const stemColors: number[] = []
    for (const category of MARKER_CATEGORIES) {
      if (!this.visible.has(category)) continue
      const markers = data.markers.filter((marker) => marker.category === category)
      if (!markers.length) continue
      const positions = new Float32Array(markers.length * 3)
      const color = new THREE.Color(this.theme.categories[category])
      markers.forEach((marker, index) => {
        const lift = category === 'healthy' ? 0.25 : MARKER_LIFT
        positions.set([marker.x, marker.z + lift, -marker.y], index * 3)
        if (category !== 'healthy') {
          stems.push(marker.x, marker.z, -marker.y, marker.x, marker.z + lift, -marker.y)
          stemColors.push(color.r, color.g, color.b, color.r, color.g, color.b)
        }
      })
      const geometry = new THREE.BufferGeometry()
      geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3))
      const points = new THREE.Points(
        geometry,
        new THREE.PointsMaterial({
          size: MARKER_PX[category],
          sizeAttenuation: false,
          map: this.glyph(category),
          transparent: true,
          alphaTest: 0.3,
          depthTest: false,
        }),
      )
      points.renderOrder = category === 'healthy' ? 5 : 10
      this.markerLayers.push({ category, points, markers })
      this.content.add(points)
    }
    if (stems.length) {
      const geometry = new THREE.BufferGeometry()
      geometry.setAttribute('position', new THREE.Float32BufferAttribute(stems, 3))
      geometry.setAttribute('color', new THREE.Float32BufferAttribute(stemColors, 3))
      const lines = new THREE.LineSegments(geometry, new THREE.LineBasicMaterial({ vertexColors: true }))
      this.markerLayers.push({ category: 'other', points: lines as unknown as THREE.Points, markers: [] })
      this.content.add(lines)
    }
    this.setHovered(null)
    this.dirty = true
  }

  private buildDevices(data: FieldSceneOut) {
    for (const device of data.devices) {
      const group = device.kind === 'drone' ? droneModel(this.theme.accent) : roverModel(this.theme.accent)
      group.position.copy(world(device.x, device.y, device.kind === 'drone' ? 3 : 0))
      group.lookAt(group.position.clone().add(this.laneDirection))
      const battery = device.battery_percent != null ? ` · ${Math.round(device.battery_percent)}%` : ''
      group.add(label(`${device.name}${battery}`, 'device', new THREE.Vector3(0, 1.6, 0)))
      this.content.add(group)
    }
  }

  private buildPendingLanes(data: FieldSceneOut) {
    for (const mission of data.missions) {
      for (const lane of mission.pending) {
        if (lane.length < 2) continue
        const line = new THREE.Line(
          new THREE.BufferGeometry().setFromPoints(lane.map(([x = 0, y = 0]) => world(x, y, 0.08))),
          new THREE.LineDashedMaterial({ color: this.theme.accent, dashSize: 1.2, gapSize: 1.2 }),
        )
        line.computeLineDistances()
        this.content.add(line)
      }
    }
  }

  // --- interação -------------------------------------------------------------

  private onPointerDown = (event: PointerEvent) => {
    this.down = { x: event.clientX, y: event.clientY }
  }

  private onPointerMove = (event: PointerEvent) => {
    if (event.buttons) return
    this.pendingMove = event
  }

  private onPointerLeave = () => {
    this.pendingMove = null
    this.setHovered(null)
    this.handlers.onHover?.(null)
  }

  private onPointerUp = (event: PointerEvent) => {
    const start = this.down
    this.down = null
    if (!start || Math.hypot(event.clientX - start.x, event.clientY - start.y) > 5) return
    const marker = this.pickMarker(event)
    if (marker) {
      this.handlers.onSelectMarker?.(marker)
      return
    }
    const plant = this.pickPlant(event)
    if (plant != null) this.handlers.onSelectPlant?.(plant)
  }

  private handleMove(event: PointerEvent) {
    const marker = this.pickMarker(event)
    this.setHovered(marker)
    const bounds = this.renderer.domElement.getBoundingClientRect()
    const x = event.clientX - bounds.left
    const y = event.clientY - bounds.top
    this.renderer.domElement.style.cursor = marker ? 'pointer' : ''
    this.handlers.onHover?.(marker ? { kind: 'marker', marker, x, y } : null)
  }

  /** O marcador mais próximo do cursor, em pixels — o tamanho dele na tela é fixo. */
  private pickMarker(event: PointerEvent): SceneMarkerOut | null {
    const bounds = this.renderer.domElement.getBoundingClientRect()
    const px = event.clientX - bounds.left
    const py = event.clientY - bounds.top
    const projected = new THREE.Vector3()
    let best: SceneMarkerOut | null = null
    let bestDistance = PICK_PX
    for (const layer of this.markerLayers) {
      const lift = layer.category === 'healthy' ? 0.25 : MARKER_LIFT
      for (const marker of layer.markers) {
        projected.set(marker.x, marker.z + lift, -marker.y).project(this.camera)
        if (projected.z > 1) continue
        const sx = ((projected.x + 1) / 2) * bounds.width
        const sy = ((1 - projected.y) / 2) * bounds.height
        const distance = Math.hypot(sx - px, sy - py)
        if (distance < bestDistance) {
          best = marker
          bestDistance = distance
        }
      }
    }
    return best
  }

  /** A planta sob o cursor: o raio cruza a altura da copa, e a planta mais perto dali. */
  private pickPlant(event: PointerEvent): number | null {
    const plants = this.data?.plants
    if (!plants?.x.length) return null
    const bounds = this.renderer.domElement.getBoundingClientRect()
    const pointer = new THREE.Vector2(
      ((event.clientX - bounds.left) / bounds.width) * 2 - 1,
      -((event.clientY - bounds.top) / bounds.height) * 2 + 1,
    )
    const raycaster = new THREE.Raycaster()
    raycaster.setFromCamera(pointer, this.camera)
    for (const level of [0.9, 0.4, 0]) {
      const hit = raycaster.ray.intersectPlane(new THREE.Plane(new THREE.Vector3(0, 1, 0), -level), new THREE.Vector3())
      if (!hit) continue
      const fx = hit.x
      const fy = -hit.z
      let best: number | null = null
      let bestDistance = 0.45
      for (let dx = -1; dx <= 1; dx += 1) {
        for (let dy = -1; dy <= 1; dy += 1) {
          for (const index of this.plantGrid.get(`${Math.floor(fx) + dx}:${Math.floor(fy) + dy}`) ?? []) {
            const distance = Math.hypot(plants.x[index]! - fx, plants.y[index]! - fy)
            if (distance < bestDistance) {
              best = index
              bestDistance = distance
            }
          }
        }
      }
      if (best != null) return best
    }
    return null
  }

  private setHovered(marker: SceneMarkerOut | null) {
    if (marker === this.hovered) return
    this.hovered = marker
    if (this.halo) {
      this.content.remove(this.halo)
      disposeObject(this.halo)
      this.halo = null
    }
    if (marker) {
      const lift = marker.category === 'healthy' ? 0.25 : MARKER_LIFT
      const geometry = new THREE.BufferGeometry()
      geometry.setAttribute('position', new THREE.Float32BufferAttribute([marker.x, marker.z + lift, -marker.y], 3))
      this.halo = new THREE.Points(
        geometry,
        new THREE.PointsMaterial({
          size: 34,
          sizeAttenuation: false,
          map: this.glyph('halo'),
          transparent: true,
          depthTest: false,
        }),
      )
      this.halo.renderOrder = 9
      this.content.add(this.halo)
    }
    this.dirty = true
  }

  // --- câmera e laço -----------------------------------------------------------

  private moveCamera(position: THREE.Vector3, target: THREE.Vector3, animate: boolean) {
    if (!animate) {
      this.camera.position.copy(position)
      this.controls.target.copy(target)
      this.controls.update()
      this.dirty = true
      return
    }
    this.tween = {
      from: { position: this.camera.position.clone(), target: this.controls.target.clone() },
      to: { position, target },
      start: performance.now(),
      duration: 1100,
    }
  }

  private frame = (time: number) => {
    if (this.pendingMove) {
      this.handleMove(this.pendingMove)
      this.pendingMove = null
    }
    if (this.tween) {
      const t = ease(Math.min(1, (time - this.tween.start) / this.tween.duration))
      this.camera.position.lerpVectors(this.tween.from.position, this.tween.to.position, t)
      this.controls.target.lerpVectors(this.tween.from.target, this.tween.to.target, t)
      if (t >= 1) this.tween = null
      this.dirty = true
    }
    const moved = this.controls.update()
    if (moved || this.dirty) {
      this.renderer.render(this.scene, this.camera)
      this.labels.render(this.scene, this.camera)
      this.dirty = false
    }
  }

  private fit() {
    const width = Math.max(1, this.container.clientWidth)
    const height = Math.max(1, this.container.clientHeight)
    this.renderer.setSize(width, height)
    this.labels.setSize(width, height)
    this.camera.aspect = width / height
    this.camera.updateProjectionMatrix()
    this.dirty = true
  }

  /** Símbolo de cada categoria — forma e cor juntas, para não depender só da cor. */
  private glyph(kind: Category | 'halo'): THREE.Texture {
    const cached = this.textures.get(kind)
    if (cached) return cached
    const size = 128
    const canvas = document.createElement('canvas')
    canvas.width = canvas.height = size
    const context = canvas.getContext('2d')!
    const outline = this.theme.dark ? '#0b1815' : '#ffffff'
    context.lineJoin = 'round'
    if (kind === 'halo') {
      context.strokeStyle = this.theme.dark ? 'rgba(255,255,255,0.9)' : 'rgba(18,32,26,0.85)'
      context.lineWidth = 10
      context.beginPath()
      context.arc(size / 2, size / 2, size / 2 - 10, 0, Math.PI * 2)
      context.stroke()
    } else {
      context.fillStyle = this.theme.categories[kind]
      context.strokeStyle = outline
      context.lineWidth = 14
      context.beginPath()
      glyphPath(context, kind, size)
      context.stroke()
      context.fill()
    }
    const texture = new THREE.CanvasTexture(canvas)
    texture.colorSpace = THREE.SRGBColorSpace
    this.textures.set(kind, texture)
    return texture
  }
}

/** O mesmo desenho do glifo, para a legenda em SVG usar a mesma forma. */
export function glyphPath(context: CanvasRenderingContext2D | Path2D, kind: Category, size: number) {
  const c = size / 2
  const r = size / 2 - 14
  switch (kind) {
    case 'pest':
      context.moveTo(c, c - r)
      context.lineTo(c + r, c)
      context.lineTo(c, c + r)
      context.lineTo(c - r, c)
      context.closePath()
      break
    case 'review':
      context.moveTo(c - r, c - r * 0.75)
      context.lineTo(c + r, c - r * 0.75)
      context.lineTo(c, c + r)
      context.closePath()
      break
    case 'other':
      context.rect(c - r * 0.78, c - r * 0.78, r * 1.56, r * 1.56)
      break
    default:
      context.moveTo(c + r, c)
      context.arc(c, c, r, 0, Math.PI * 2)
  }
}

function label(text: string, kind: 'device' | 'zone', position: THREE.Vector3): CSS2DObject {
  const element = document.createElement('div')
  element.textContent = text
  element.className = kind === 'device' ? 'scene-label scene-label--device' : 'scene-label scene-label--zone'
  const object = new CSS2DObject(element)
  object.position.copy(position)
  return object
}

function roverModel(accent: string): THREE.Group {
  const group = new THREE.Group()
  const body = new THREE.Mesh(
    new THREE.BoxGeometry(0.62, 0.32, 1.0),
    new THREE.MeshStandardMaterial({ color: accent, roughness: 0.45, metalness: 0.2 }),
  )
  body.position.y = 0.42
  group.add(body)
  const tire = new THREE.MeshStandardMaterial({ color: '#1d2320', roughness: 0.9 })
  for (const [x, z] of [
    [-0.36, -0.34],
    [0.36, -0.34],
    [-0.36, 0.34],
    [0.36, 0.34],
  ] as const) {
    const wheel = new THREE.Mesh(new THREE.CylinderGeometry(0.2, 0.2, 0.12, 18).rotateZ(Math.PI / 2), tire)
    wheel.position.set(x, 0.2, z)
    group.add(wheel)
  }
  const mast = new THREE.Mesh(
    new THREE.CylinderGeometry(0.025, 0.025, 0.7, 8),
    new THREE.MeshStandardMaterial({ color: '#d7dbd8' }),
  )
  mast.position.set(0, 0.92, -0.3)
  group.add(mast)
  const lidar = new THREE.Mesh(
    new THREE.CylinderGeometry(0.09, 0.09, 0.09, 20),
    new THREE.MeshStandardMaterial({ color: '#1d2320', roughness: 0.3, metalness: 0.5 }),
  )
  lidar.position.set(0, 1.3, -0.3)
  group.add(lidar)
  return group
}

function droneModel(accent: string): THREE.Group {
  const group = new THREE.Group()
  const material = new THREE.MeshStandardMaterial({ color: accent, roughness: 0.4 })
  group.add(new THREE.Mesh(new THREE.BoxGeometry(0.4, 0.14, 0.4), material))
  for (const angle of [0.785, 2.356, 3.927, 5.498]) {
    const arm = new THREE.Mesh(new THREE.BoxGeometry(0.7, 0.04, 0.06), material)
    arm.rotation.y = angle
    arm.position.set(Math.cos(angle) * 0.35, 0, -Math.sin(angle) * 0.35)
    group.add(arm)
    const rotor = new THREE.Mesh(
      new THREE.CylinderGeometry(0.22, 0.22, 0.01, 20),
      new THREE.MeshStandardMaterial({ color: '#d7dbd8', transparent: true, opacity: 0.6 }),
    )
    rotor.position.set(Math.cos(angle) * 0.68, 0.06, -Math.sin(angle) * 0.68)
    group.add(rotor)
  }
  return group
}

function disposeObject(object: THREE.Object3D) {
  object.traverse((child) => {
    const item = child as THREE.Mesh
    item.geometry?.dispose()
    const material = item.material as THREE.Material | THREE.Material[] | undefined
    if (Array.isArray(material)) material.forEach((entry) => entry.dispose())
    else material?.dispose()
    if (child instanceof CSS2DObject) child.element.remove()
  })
}

/** O retângulo que as passadas cobriram, em metros do talhão. */
function scannedBox(data: FieldSceneOut): [number, number, number, number] | null {
  let minX = Infinity
  let maxX = -Infinity
  let minY = Infinity
  let maxY = -Infinity
  for (const scan of data.scans) {
    for (const [x = 0, y = 0] of scan.path) {
      minX = Math.min(minX, x - scan.reach_m)
      maxX = Math.max(maxX, x + scan.reach_m)
      minY = Math.min(minY, y - scan.reach_m)
      maxY = Math.max(maxY, y + scan.reach_m)
    }
  }
  return Number.isFinite(minX) ? [minX, maxX, minY, maxY] : null
}

function hash(x: number, y: number): number {
  const value = Math.sin(x * 12.9898 + y * 78.233) * 43758.5453
  return value - Math.floor(value)
}

function clamp01(value: number): number {
  return Math.min(1, Math.max(0, value))
}

let SRGB: Float32Array | null = null
function srgbTable(): Float32Array {
  if (!SRGB) {
    SRGB = new Float32Array(256)
    // A cor do PLY é sRGB; o three.js trabalha em linear.
    for (let index = 0; index < 256; index += 1) {
      const value = index / 255
      SRGB[index] = value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4
    }
  }
  return SRGB
}
