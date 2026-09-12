/**
 * Leitor da nuvem de pontos que o rover envia.
 *
 * Só o layout do contrato (`docs/ROVER_INTEGRATION.md`): PLY binário little
 * endian, `x y z` em float e `red green blue` em uchar — 15 bytes por ponto. O
 * servidor já recusou qualquer outro na entrada, então aqui não há variações a
 * tratar: é ler o cabeçalho, conferir o tamanho e copiar.
 */

export type PointCloud = {
  count: number
  /** x, y, z em metros no plano da passada (x leste, y norte, z para cima). */
  positions: Float32Array
  colors: Uint8Array
}

const STRIDE = 15
const END = new TextEncoder().encode('end_header\n')

export function parsePly(buffer: ArrayBuffer): PointCloud {
  const bytes = new Uint8Array(buffer)
  const end = indexOf(bytes, END, 4096)
  if (end < 0) throw new Error('A nuvem não é um PLY do contrato.')

  const header = new TextDecoder('ascii').decode(bytes.subarray(0, end))
  const vertices = /element vertex (\d+)/.exec(header)
  if (!header.startsWith('ply') || !header.includes('binary_little_endian') || !vertices) {
    throw new Error('Cabeçalho PLY fora do contrato.')
  }

  const count = Number(vertices[1])
  const offset = end + END.length
  if (buffer.byteLength - offset < count * STRIDE) throw new Error('Nuvem truncada.')

  const view = new DataView(buffer, offset)
  const positions = new Float32Array(count * 3)
  const colors = new Uint8Array(count * 3)
  for (let index = 0; index < count; index += 1) {
    const at = index * STRIDE
    positions[index * 3] = view.getFloat32(at, true)
    positions[index * 3 + 1] = view.getFloat32(at + 4, true)
    positions[index * 3 + 2] = view.getFloat32(at + 8, true)
    colors[index * 3] = view.getUint8(at + 12)
    colors[index * 3 + 1] = view.getUint8(at + 13)
    colors[index * 3 + 2] = view.getUint8(at + 14)
  }
  return { count, positions, colors }
}

function indexOf(haystack: Uint8Array, needle: Uint8Array, limit: number): number {
  const last = Math.min(limit, haystack.length) - needle.length
  outer: for (let start = 0; start <= last; start += 1) {
    for (let offset = 0; offset < needle.length; offset += 1) {
      if (haystack[start + offset] !== needle[offset]) continue outer
    }
    return start
  }
  return -1
}
