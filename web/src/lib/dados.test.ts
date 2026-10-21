import { describe, expect, it } from 'vitest'

import { avisoText, bytesText, classesOrdenadas, fracaoTone, prioridadeText } from './dados'

describe('orçamento de dados', () => {
  it('bytes em unidades decimais, como a Starlink cobra', () => {
    expect(bytesText(0)).toBe('0 B')
    expect(bytesText(999)).toBe('999 B')
    expect(bytesText(1500)).toBe('1,50 kB')
    expect(bytesText(2_000_000_000)).toBe('2,00 GB')
    expect(bytesText(123_400_000)).toBe('123 MB')
    expect(bytesText(null)).toBe('sem dado')
  })

  it('tom pelo teto, e a tempestade acima de tudo', () => {
    expect(fracaoTone(0.5)).toBe('good')
    expect(fracaoTone(0.85)).toBe('warning')
    expect(fracaoTone(1.2)).toBe('critical')
    expect(fracaoTone(0.1, true)).toBe('serious')
    expect(fracaoTone(null)).toBe('neutral')
  })

  it('o que ainda sobe, em palavras', () => {
    expect(prioridadeText(1)).toContain('nunca corta')
    expect(prioridadeText(6)).toBe('tudo')
    expect(prioridadeText(undefined)).toBe('sem dado')
  })

  it('classes da maior para a menor, sem as vazias', () => {
    const c = classesOrdenadas({ telemetria: 10, arquivos: 900, registros: 50, video: null })
    expect(c.map((x) => x.rotulo)).toEqual(['Imagens', 'Resultados e eventos', 'Telemetria'])
  })

  it('avisos em português', () => {
    expect(avisoText({ tipo: 'EVENT_STORM', em: '', severidade: null, missao: null, dados: { estado: 'inicio', taxa_eventos: 0.97 } }))
      .toBe('Tempestade de eventos (97% dos quadros): originais retidos no disco')
    expect(avisoText({ tipo: 'DATA_BUDGET', em: '', severidade: null, missao: null, dados: { nivel: 0.8 } })).toBe('Usou 80% do teto do dia')
  })
})
