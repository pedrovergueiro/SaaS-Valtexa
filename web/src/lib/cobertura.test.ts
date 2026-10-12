import { describe, expect, it } from 'vitest'

import { type MapaCobertura, area_m2, contagem, fracoes, grade } from './cobertura'

const mapa = (celulas: MapaCobertura['celulas']): MapaCobertura => ({
  versao: 1,
  origem: [-22.4145, -45.4515],
  celula_m: 10,
  celulas,
  zonas_mortas: [],
  repetidoras: [],
})

describe('grade do mapa de cobertura', () => {
  it('põe o norte para cima e começa do canto', () => {
    const g = grade(mapa({ '-1,0': 'bom', '2,0': 'marginal', '0,3': 'morto' }))
    expect([g.colunas, g.linhas]).toEqual([4, 4])
    expect([g.largura_m, g.altura_m]).toEqual([40, 40])
    const morta = g.celulas.find((c) => c.classe === 'morto')!
    expect([morta.x, morta.y]).toEqual([1, 0]) // j = 3 é a linha de cima
    const boa = g.celulas.find((c) => c.classe === 'bom')!
    expect([boa.x, boa.y]).toEqual([0, 3])
    expect(g.posicao(2, 0)).toEqual({ x: 3, y: 3 })
    expect(g.posicao(9, 9)).toBeNull()
  })

  it('ignora chave malformada e mapa vazio não quebra', () => {
    expect(grade(mapa({ 'a,b': 'bom', '0,0': 'bom' })).celulas).toHaveLength(1)
    const vazio = grade(mapa({}))
    expect([vazio.colunas, vazio.linhas, vazio.posicao(0, 0)]).toEqual([0, 0, null])
  })

  it('conta e mede cada classe', () => {
    const m = mapa({ '0,0': 'bom', '0,1': 'bom', '1,0': 'marginal', '1,1': 'morto' })
    expect(contagem(m)).toEqual({ bom: 2, marginal: 1, morto: 1 })
    expect(fracoes(m)).toEqual({ bom: 0.5, marginal: 0.25, morto: 0.25 })
    expect(fracoes(mapa({}))).toEqual({ bom: 0, marginal: 0, morto: 0 })
    expect(area_m2(m, 3)).toBe(300)
  })
})
