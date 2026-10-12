/**
 * A leitura de coordenadas coladas pelo produtor.
 *
 * Esta é a única peça do console que decide sozinha onde fica um lugar. Errar
 * aqui não dá erro de tela: dá um ponto plausível no lugar errado, que só
 * aparece quando o rover sai andando. Por isso ela tem teste e o resto do
 * console não — o resto tem o servidor embaixo para recusar.
 */
import { describe, expect, it } from 'vitest'

import { parseCoords } from './geo'

/** O par que o Google Maps dá para a fazenda de demonstração, em Minas. */
const LAT = -21.9029
const LON = -45.8624

function perto(recebido: number | undefined, esperado: number, tolerancia = 1e-4) {
  expect(Math.abs((recebido ?? 0) - esperado)).toBeLessThan(tolerancia)
}

describe('decimal, como o Google Maps copia', () => {
  it('lê latitude primeiro e devolve [lon, lat]', () => {
    const { points } = parseCoords('-21.9029, -45.8624')
    expect(points).toHaveLength(1)
    perto(points[0]?.[0], LON)
    perto(points[0]?.[1], LAT)
  })

  it('aceita separado por espaço', () => {
    const { points } = parseCoords('-21.9029 -45.8624')
    perto(points[0]?.[1], LAT)
  })

  it('aceita vírgula decimal, como o Excel brasileiro exporta', () => {
    const { points } = parseCoords('-21,9029; -45,8624')
    perto(points[0]?.[0], LON)
    perto(points[0]?.[1], LAT)
  })

  it('lê várias linhas como um polígono', () => {
    const { points } = parseCoords('-21.9029, -45.8624\n-21.9040, -45.8620\n-21.9035, -45.8610')
    expect(points).toHaveLength(3)
  })

  it('reconhece longitude no primeiro número quando ela passa de 90', () => {
    const { points, aviso } = parseCoords('-120.5, 35.2')
    perto(points[0]?.[0], -120.5)
    perto(points[0]?.[1], 35.2)
    expect(aviso).toMatch(/longitude/i)
  })
})

describe('graus, minutos e segundos', () => {
  it('lê o formato que o Google Maps mostra no painel do lugar', () => {
    const { points } = parseCoords(`21°54'10.4"S 45°51'44.6"W`)
    perto(points[0]?.[1], -21.9029, 1e-3)
    perto(points[0]?.[0], -45.8624, 1e-3)
  })

  it('aceita O de Oeste, que é como o português escreve', () => {
    const { points } = parseCoords(`21°54'10.4"S 45°51'44.6"O`)
    perto(points[0]?.[0], -45.8624, 1e-3)
  })

  it('aceita sem os segundos', () => {
    const { points } = parseCoords(`21°54.2'S 45°51.7'W`)
    perto(points[0]?.[1], -21.9033, 1e-3)
  })

  it('respeita o hemisfério norte e leste', () => {
    const { points } = parseCoords(`48°51'30"N 2°17'40"E`)
    perto(points[0]?.[1], 48.8583, 1e-3)
    perto(points[0]?.[0], 2.2944, 1e-3)
  })

  it('não confunde os três números de um DMS com um par decimal', () => {
    // A regressão que este arquivo existe para impedir: antes, `21°54'10.4"S`
    // virava latitude 21, longitude 54 — um ponto no Sudão, aceito em silêncio.
    const { points } = parseCoords(`21°54'10.4"S 45°51'44.6"W`)
    expect(Math.abs(points[0]?.[0] ?? 0)).toBeGreaterThan(40)
    expect(points[0]?.[1]).toBeLessThan(0)
  })
})

describe('GeoJSON colado inteiro', () => {
  it('aproveita o anel sem adivinhar a ordem', () => {
    const { points, aviso } = parseCoords(
      '{"type":"Polygon","coordinates":[[[-45.8624,-21.9029],[-45.8620,-21.9040],[-45.8610,-21.9035]]]}',
    )
    expect(points).toHaveLength(3)
    perto(points[0]?.[0], LON)
    expect(aviso).toMatch(/GeoJSON/i)
  })
})

describe('o que ele recusa', () => {
  it('texto vazio não vira ponto nenhum', () => {
    expect(parseCoords('   ').points).toEqual([])
  })

  it('texto sem número avisa em vez de inventar', () => {
    const { points, aviso } = parseCoords('fazenda do compadre')
    expect(points).toEqual([])
    expect(aviso).toMatch(/nenhuma coordenada/i)
  })

  it('avisa quando o ponto cai fora do Brasil', () => {
    const { aviso } = parseCoords('48.8583, 2.2944')
    expect(aviso).toMatch(/fora do Brasil/i)
  })
})
