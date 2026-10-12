/**
 * Achar a fazenda: o que a pessoa digita na caixa "endereço ou coordenadas".
 *
 * Coordenada e link do Google Maps são lidos aqui, sem rede (e sem gastar cota):
 * `-21.36, -45.51`, `21°22'S 45°30'W`, `https://www.google.com/maps/@-21.36,-45.51,17z`,
 * `https://maps.google.com/?q=-21.36,-45.51`, o `!3d…!4d…` do link de um lugar. O resto é
 * endereço e vai ao servidor (`GET /v1/mapa/localizar`).
 */
import { parseCoords } from './geo'

export type Lugar = {
  nome: string
  lat: number
  lon: number
  tipo: string | null
  fonte: 'google' | 'osm' | 'coordenadas'
  /** Sul, oeste, norte, leste. */
  caixa: [number, number, number, number] | null
}

const NUM = String.raw`(-?\d{1,3}(?:\.\d+)?)`

/** A coordenada de um link do Google Maps (o ponto do lugar, se houver; se não, a câmera). */
export function coordenadaDeLink(texto: string): [number, number] | null {
  if (!/google\.[a-z.]+\/maps|maps\.google\.|goo\.gl\/maps|maps\.app\.goo\.gl/i.test(texto)) return null
  const lugar = new RegExp(String.raw`!3d${NUM}!4d${NUM}`).exec(texto)
  const q = new RegExp(String.raw`[?&](?:q|query|ll|center|destination)=${NUM}(?:,|%2C)\s*${NUM}`, 'i').exec(texto)
  const camera = new RegExp(String.raw`@${NUM},${NUM}`).exec(texto)
  const achado = lugar ?? q ?? camera
  if (!achado) return null
  const lat = Number(achado[1])
  const lon = Number(achado[2])
  return Math.abs(lat) <= 90 && Math.abs(lon) <= 180 ? [lat, lon] : null
}

export type Leitura =
  | { tipo: 'ponto'; lugar: Lugar }
  | { tipo: 'contorno'; pontos: number[][] }
  | { tipo: 'endereco'; texto: string }
  | { tipo: 'curto' }

/** O que fazer com o que foi digitado: ir a um ponto, desenhar um contorno ou buscar. */
export function leia(texto: string): Leitura {
  const limpo = texto.trim()
  const doLink = coordenadaDeLink(limpo)
  if (doLink)
    return {
      tipo: 'ponto',
      lugar: ponto(doLink[0], doLink[1], 'Ponto do link do Google Maps'),
    }
  if (/^link curto/i.test(limpo) || /maps\.app\.goo\.gl|goo\.gl\/maps/i.test(limpo)) {
    // Link curto não traz a coordenada: só abrindo. Cai na busca, que avisa.
    return { tipo: 'endereco', texto: limpo }
  }
  // Só números, sinais e símbolos de grau: é coordenada. Com letras (fora N/S/E/W/O
  // de hemisfério), é endereço — "Rodovia MG-167 km 12" tem números e não é ponto.
  const semHemisferio = limpo.replace(/\b[NSEWO]\b/gi, '').replace(/(\d)\s*[NSEWO]\b/gi, '$1')
  if (!/[a-zà-ú]/i.test(semHemisferio)) {
    const { points } = parseCoords(limpo)
    if (points.length === 1) {
      const [lon = 0, lat = 0] = points[0]!
      return {
        tipo: 'ponto',
        lugar: ponto(lat, lon, `${lat.toFixed(5)}, ${lon.toFixed(5)}`),
      }
    }
    if (points.length >= 3) return { tipo: 'contorno', pontos: points }
  }
  if (limpo.length < 3) return { tipo: 'curto' }
  return { tipo: 'endereco', texto: limpo }
}

function ponto(lat: number, lon: number, nome: string): Lugar {
  return {
    nome,
    lat,
    lon,
    tipo: 'coordenada',
    fonte: 'coordenadas',
    caixa: null,
  }
}

/**
 * Para onde o mapa vai: a caixa do lugar (cidade inteira) ou o ponto num zoom de lavoura.
 * Caixa de mais de ~30 km (um estado, um país) vira ponto: ninguém desenha talhão daí.
 */
export function enquadramento(
  lugar: Lugar,
): { caixa: [[number, number], [number, number]] } | { ponto: [number, number]; zoom: number } {
  const c = lugar.caixa
  if (c && Math.abs(c[2] - c[0]) < 0.3 && Math.abs(c[3] - c[1]) < 0.3 && (c[2] - c[0]) * (c[3] - c[1]) > 1e-8) {
    return {
      caixa: [
        [c[0], c[1]],
        [c[2], c[3]],
      ],
    }
  }
  return {
    ponto: [lugar.lat, lugar.lon],
    zoom: lugar.fonte === 'coordenadas' ? 18 : 16,
  }
}
