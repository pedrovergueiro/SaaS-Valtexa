/**
 * Geometria das plantas da cópia 3D.
 *
 * Cada planta é uma instância da mesma malha, escalada pelo que o rover mediu:
 * altura no eixo vertical, diâmetro de copa nos outros dois. A malha base tem
 * altura 1 e copa 1, e poucos triângulos — um talhão tem dezenas de milhares de
 * plantas e todas precisam caber na placa de vídeo de um notebook.
 *
 * O desenho não é a planta medida: é um símbolo dimensionado por ela. A forma
 * real de cada planta está na nuvem de pontos, que o console abre por rua.
 */
import * as THREE from 'three'

type Builder = {
  positions: number[]
  shades: number[]
  indices: number[]
}

function vertex(builder: Builder, x: number, y: number, z: number, shade: number): number {
  builder.positions.push(x, y, z)
  builder.shades.push(shade, shade, shade)
  return builder.positions.length / 3 - 1
}

function quad(builder: Builder, a: number, b: number, c: number, d: number) {
  builder.indices.push(a, b, c, a, c, d)
}

function finish(builder: Builder): THREE.BufferGeometry {
  const geometry = new THREE.BufferGeometry()
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(builder.positions, 3))
  geometry.setAttribute('color', new THREE.Float32BufferAttribute(builder.shades, 3))
  geometry.setIndex(builder.indices)
  geometry.computeVertexNormals()
  geometry.computeBoundingSphere()
  return geometry
}

/** Milho: colmo e quatro folhas arqueadas. ~40 triângulos. */
export function cornGeometry(): THREE.BufferGeometry {
  const builder: Builder = { positions: [], shades: [], indices: [] }

  // Colmo: prisma de quatro faces, mais escuro na base.
  const radius = 0.014
  const top = 0.92
  const ring = (y: number, shade: number) =>
    [0, 1, 2, 3].map((side) => {
      const angle = (side / 4) * Math.PI * 2
      return vertex(builder, Math.cos(angle) * radius, y, Math.sin(angle) * radius, shade)
    })
  const bottom = ring(0, 0.55)
  const upper = ring(top, 0.9)
  for (let side = 0; side < 4; side += 1) {
    const next = (side + 1) % 4
    quad(builder, bottom[side]!, bottom[next]!, upper[next]!, upper[side]!)
  }

  // Folhas: tiras de três segmentos que sobem e caem, em espiral.
  const leaves = 4
  const segments = 3
  for (let leaf = 0; leaf < leaves; leaf += 1) {
    const angle = leaf * 2.4 + 0.4
    const dx = Math.cos(angle)
    const dz = Math.sin(angle)
    const attach = 0.24 + 0.17 * leaf
    const length = 0.5 * (1 - (0.28 * leaf) / leaves)
    let previous: [number, number] | null = null
    for (let step = 0; step <= segments; step += 1) {
      const t = step / segments
      const reach = length * t
      const y = attach + length * (0.5 * t - 0.62 * t * t) * 1.4
      const half = 0.05 * (1 - 0.85 * t) + 0.004
      const cx = dx * reach
      const cz = dz * reach
      const shade = 0.72 + 0.28 * t
      const left = vertex(builder, cx - dz * half, y, cz + dx * half, shade)
      const right = vertex(builder, cx + dz * half, y, cz - dx * half, shade)
      if (previous) quad(builder, previous[0], previous[1], right, left)
      previous = [left, right]
    }
  }
  return finish(builder)
}

/**
 * Cafeeiro: haste única e nove pares de ramos laterais, copa cheia. ~130 triângulos.
 *
 * A arquitetura do café não é um arbusto redondo — é uma haste ortotrópica com
 * ramos plagiotrópicos em pares opostos, cada par girado em relação ao de baixo,
 * e comprimento que diminui para o topo. É isso que dá à lavoura vista de cima
 * a textura de ruas fechadas da foto; uma esfera produziria um campo de bolhas
 * que não se parece com cafezal nenhum.
 */
export function coffeeGeometry(): THREE.BufferGeometry {
  const builder: Builder = { positions: [], shades: [], indices: [] }

  // Haste: prisma de quatro faces, escura na base e clara no ponteiro.
  const radius = 0.03
  const top = 0.98
  const ring = (y: number, shade: number, escala = 1) =>
    [0, 1, 2, 3].map((side) => {
      const angle = (side / 4) * Math.PI * 2
      const r = radius * escala
      return vertex(builder, Math.cos(angle) * r, y, Math.sin(angle) * r, shade)
    })
  const base = ring(0, 0.38)
  const meio = ring(top * 0.5, 0.55, 0.85)
  const ponteiro = ring(top, 0.8, 0.4)
  for (let side = 0; side < 4; side += 1) {
    const next = (side + 1) % 4
    quad(builder, base[side]!, base[next]!, meio[next]!, meio[side]!)
    quad(builder, meio[side]!, meio[next]!, ponteiro[next]!, ponteiro[side]!)
  }

  // Ramos plagiotrópicos: nove pares opostos, do terço inferior ao ponteiro.
  // Nove e não seis porque o cafeeiro adulto fecha a copa — com poucos ramos a
  // planta vista de cima vira uma cruz, e a lavoura vira um campo de cruzes em
  // vez da rua contínua que se vê na foto aérea.
  const pares = 9
  for (let par = 0; par < pares; par += 1) {
    const t = par / (pares - 1)
    const altura = 0.14 + 0.8 * t
    // Copa cheia embaixo, afilando para cima: perfil de cafeeiro formado.
    const comprimento = 0.5 * (1 - 0.52 * t * t)
    const giro = par * 0.9 // cada par gira ~52° sobre o de baixo
    for (const lado of [0, Math.PI]) {
      const angle = giro + lado
      const dx = Math.cos(angle)
      const dz = Math.sin(angle)
      let anterior: [number, number] | null = null
      // Três segmentos: o ramo cai na ponta, como ramo carregado de fruto.
      for (let passo = 0; passo <= 3; passo += 1) {
        const u = passo / 3
        const alcance = comprimento * u
        const y = altura - 0.16 * comprimento * u * u
        const meia = 0.075 * Math.sin(Math.PI * (0.25 + 0.6 * u)) + 0.008
        const cx = dx * alcance
        const cz = dz * alcance
        const shade = 0.6 + 0.34 * u
        const esquerda = vertex(builder, cx - dz * meia, y, cz + dx * meia, shade)
        const direita = vertex(builder, cx + dz * meia, y, cz - dx * meia, shade)
        if (anterior) quad(builder, anterior[0], anterior[1], direita, esquerda)
        anterior = [esquerda, direita]
      }
    }
  }
  return finish(builder)
}

/** Copa arredondada, para cultura sem geometria própria. */
export function bushGeometry(): THREE.BufferGeometry {
  const geometry = new THREE.IcosahedronGeometry(0.5, 1)
  geometry.translate(0, 0.5, 0)
  const count = geometry.getAttribute('position').count
  const shades = new Float32Array(count * 3)
  const positions = geometry.getAttribute('position')
  for (let index = 0; index < count; index += 1) {
    const shade = 0.6 + 0.4 * positions.getY(index)
    shades.set([shade, shade, shade], index * 3)
  }
  geometry.setAttribute('color', new THREE.BufferAttribute(shades, 3))
  return geometry
}

export function geometryForCrop(crop: string): THREE.BufferGeometry {
  const cultura = (crop || '').toLowerCase()
  if (cultura === 'corn' || cultura === 'milho') return cornGeometry()
  if (cultura === 'coffee' || cultura === 'cafe' || cultura === 'café') return coffeeGeometry()
  return bushGeometry()
}
