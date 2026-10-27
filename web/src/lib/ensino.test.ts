import { describe, expect, it } from 'vitest'

import { caixaDoArraste, condicaoDoFormulario, corpoDaExplicacao, EXPLICACAO_VAZIA, pontoNormalizado, tendencia, tomDoVeredito, type RegraForm } from './ensino'

describe('lesão marcada na foto', () => {
  it('arraste em qualquer direção vira a mesma caixa, dentro da foto', () => {
    expect(caixaDoArraste({ x: 0.5, y: 0.6 }, { x: 0.2, y: 0.1 })).toEqual({ x: 0.2, y: 0.1, w: 0.3, h: 0.5 })
    expect(caixaDoArraste({ x: 0.9, y: 0.9 }, { x: 1.4, y: 1.2 })).toEqual({ x: 0.9, y: 0.9, w: 0.1, h: 0.1 })
  })

  it('clique sem arrastar não vira lesão', () => {
    expect(caixaDoArraste({ x: 0.5, y: 0.5 }, { x: 0.502, y: 0.6 })).toBeNull()
  })

  it('normaliza pelo retângulo da foto na tela', () => {
    expect(pontoNormalizado(150, 100, { left: 100, top: 50, width: 200, height: 100 })).toEqual({ x: 0.25, y: 0.5 })
    expect(pontoNormalizado(0, 0, { left: 100, top: 50, width: 200, height: 100 })).toEqual({ x: 0, y: 0 })
  })
})

describe('o porquê do agrônomo', () => {
  it('explicação vazia não vai', () => {
    expect(corpoDaExplicacao({ ...EXPLICACAO_VAZIA, porque: '   ' })).toBeNull()
    expect(corpoDaExplicacao({ ...EXPLICACAO_VAZIA, face: 'abaxial' })?.face).toBe('abaxial')
  })

  it('tendência só com meses de pelo menos 5 casos', () => {
    expect(tendencia([{ mes: '2026-09', casos: 3, ia_acertou: 0, taxa: 0 }])).toBeNull()
    expect(
      tendencia([
        { mes: '2026-08', casos: 10, ia_acertou: 4, taxa: 0.4 },
        { mes: '2026-09', casos: 2, ia_acertou: 2, taxa: 1 },
        { mes: '2026-10', casos: 10, ia_acertou: 7, taxa: 0.7 },
      ]),
    ).toBe(0.3)
  })
})

describe('regra do agrônomo', () => {
  const base: RegraForm = { cultura: 'coffee', doenca: 'Rust', texto: 'x', variavel: 'chuva_mm', janela: '14', operador: '<', valor: '10,5', meses: '6, 7 8', efeito: 'aumenta' }

  it('condição de clima vai com janela, operador e valor (vírgula vira ponto)', () => {
    expect(condicaoDoFormulario(base)).toEqual({ variavel: 'chuva_mm', janela_dias: 14, operador: '<', valor: 10.5 })
  })

  it('condição de mês vai com a lista de meses', () => {
    expect(condicaoDoFormulario({ ...base, variavel: 'mes' })).toEqual({ variavel: 'mes', meses: [6, 7, 8] })
  })

  it('só "sustentada" é verde; "poucos dados" não é a favor nem contra', () => {
    expect(tomDoVeredito('sustentada')).toBe('good')
    expect(tomDoVeredito('contrariada')).toBe('critical')
    expect(tomDoVeredito('poucos_dados')).toBe('neutral')
  })
})
