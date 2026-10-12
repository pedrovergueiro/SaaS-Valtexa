import { describe, expect, it } from 'vitest'

import { coordenadaDeLink, enquadramento, leia } from './localizar'

describe('link do Google Maps', () => {
  it('pega o ponto do lugar antes da câmera', () => {
    const url =
      'https://www.google.com/maps/place/Fazenda+Santa+Rita/@-21.3700,-45.5200,15z/data=!3m1!4b1!4m6!3m5!1s0x0:0x0!8m2!3d-21.3667!4d-45.5122'
    expect(coordenadaDeLink(url)).toEqual([-21.3667, -45.5122])
  })
  it('lê a câmera e o ?q=', () => {
    expect(coordenadaDeLink('https://www.google.com/maps/@-21.9,-45.86,17z')).toEqual([-21.9, -45.86])
    expect(coordenadaDeLink('https://maps.google.com/?q=-21.9,-45.86')).toEqual([-21.9, -45.86])
    expect(coordenadaDeLink('https://maps.google.com/?q=-21.9%2C-45.86')).toEqual([-21.9, -45.86])
  })
  it('não é link do Google: nada', () => {
    expect(coordenadaDeLink('Três Pontas MG')).toBeNull()
    expect(coordenadaDeLink('https://exemplo.com/@-21.9,-45.86')).toBeNull()
  })
})

describe('o que foi digitado', () => {
  it('coordenada decimal e em graus vão direto, sem rede', () => {
    const decimal = leia('-21.36670, -45.51220')
    expect(decimal.tipo).toBe('ponto')
    if (decimal.tipo === 'ponto') expect([decimal.lugar.lat, decimal.lugar.lon]).toEqual([-21.3667, -45.5122])
    const graus = leia(`21°22'00.1"S 45°30'43.9"W`)
    expect(graus.tipo).toBe('ponto')
    if (graus.tipo === 'ponto') {
      expect(graus.lugar.lat).toBeCloseTo(-21.3667, 3)
      expect(graus.lugar.lon).toBeCloseTo(-45.5122, 3)
    }
  })
  it('três pontos ou mais desenham o contorno', () => {
    const r = leia('-21.904, -45.862\n-21.901, -45.861\n-21.903, -45.859')
    expect(r.tipo).toBe('contorno')
  })
  it('endereço com número continua endereço', () => {
    expect(leia('Rodovia MG-167 km 12, Três Pontas')).toEqual({
      tipo: 'endereco',
      texto: 'Rodovia MG-167 km 12, Três Pontas',
    })
    expect(leia('Fazenda Santa Rita')).toEqual({
      tipo: 'endereco',
      texto: 'Fazenda Santa Rita',
    })
    expect(leia('ab')).toEqual({ tipo: 'curto' })
  })
})

describe('para onde o mapa vai', () => {
  it('cidade: a caixa; estado inteiro ou ponto: zoom de lavoura', () => {
    const cidade = enquadramento({
      nome: 'Três Pontas',
      lat: -21.36,
      lon: -45.51,
      tipo: 'town',
      fonte: 'osm',
      caixa: [-21.4, -45.55, -21.33, -45.47],
    })
    expect(cidade).toEqual({
      caixa: [
        [-21.4, -45.55],
        [-21.33, -45.47],
      ],
    })
    const estado = enquadramento({
      nome: 'MG',
      lat: -18.5,
      lon: -44.5,
      tipo: 'state',
      fonte: 'osm',
      caixa: [-22.9, -51.0, -14.2, -39.8],
    })
    expect(estado).toEqual({ ponto: [-18.5, -44.5], zoom: 16 })
    const coord = enquadramento({
      nome: 'x',
      lat: -21.9,
      lon: -45.8,
      tipo: 'coordenada',
      fonte: 'coordenadas',
      caixa: null,
    })
    expect(coord).toEqual({ ponto: [-21.9, -45.8], zoom: 18 })
  })
})
