/**
 * Área de polígono no navegador — a mesma aproximação local de
 * `valtexa/services/geo.py`, só para mostrar ao usuário enquanto ele desenha.
 * O número que vale é o que o servidor calcula ao gravar.
 */
const METERS_PER_DEGREE_LAT = 111_320

export function areaHa(ring: number[][]): number {
  if (ring.length < 3) return 0
  const lat0 = ring.reduce((sum, point) => sum + (point[1] ?? 0), 0) / ring.length
  const scaleLon = METERS_PER_DEGREE_LAT * Math.cos((lat0 * Math.PI) / 180)
  let total = 0
  for (let index = 0; index < ring.length; index += 1) {
    const a = ring[index] ?? [0, 0]
    const b = ring[(index + 1) % ring.length] ?? [0, 0]
    total += (a[0] ?? 0) * scaleLon * ((b[1] ?? 0) * METERS_PER_DEGREE_LAT) - (b[0] ?? 0) * scaleLon * ((a[1] ?? 0) * METERS_PER_DEGREE_LAT)
  }
  return Math.abs(total) / 2 / 10_000
}
