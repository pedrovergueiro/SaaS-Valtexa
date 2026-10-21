import { describe, expect, it } from 'vitest'

import { avaliacaoTom, cenarioTexto, origemTexto, origemTom, podeRevisar, premissasNaoMedidas, revisaoValida, valorPremissa, type Premissa } from './planejamento'

describe('planejamento de apoio à decisão', () => {
  it('premissa não medida ou simulada é marcada para desconfiança', () => {
    const ps: Premissa[] = [
      { codigo: 'a', texto: '', valor: 1, origem: 'padrao' },
      { codigo: 'b', texto: '', valor: 1, origem: 'simulado' },
      { codigo: 'c', texto: '', valor: 1, origem: 'medido' },
      { codigo: 'd', texto: '', valor: 1, origem: 'pedido' },
    ]
    expect(premissasNaoMedidas(ps)).toBe(2)
    expect(origemTom('simulado')).toBe('warning')
    expect(origemTexto('padrao')).toBe('Padrão (não medido)')
    expect(origemTom('medido')).toBe('good')
  })

  it('a revisão segue a capacidade do tipo, como a API', () => {
    const agronomo = (c: string) => ['diagnosis:review', 'mission:create', 'product:manage'].includes(c)
    const operador = (c: string) => c === 'mission:create'
    expect(podeRevisar('fitossanitario', agronomo)).toBe(true)
    expect(podeRevisar('fitossanitario', operador)).toBe(false)
    expect(podeRevisar('robotico', operador)).toBe(true)
    expect(podeRevisar('insumos', operador)).toBe(false)
  })

  it('recusar ou pedir ajuste exige comentário', () => {
    expect(revisaoValida('aceito', '')).toBe(true)
    expect(revisaoValida('recusado', '  ')).toBe(false)
    expect(revisaoValida('ajustar', 'sem a rua 9')).toBe(true)
  })

  it('formata valores e cenários', () => {
    expect(valorPremissa(null)).toBe('—')
    expect(valorPremissa({})).toBe('(nenhum)')
    expect(valorPremissa(false)).toBe('não')
    expect(valorPremissa(88000)).toBe('88.000')
    expect(cenarioTexto({ p10: 8, p50: 12.5, p90: 19.5 })).toBe('12,5 L (8–19,5 L)')
    expect(cenarioTexto(null)).toBe('—')
  })

  it('avaliação da rotação', () => {
    expect(avaliacaoTom('passaria do limite de 2 aplicação(ões) seguidas do grupo FRAC 3')).toBe('critical')
    expect(avaliacaoTom('repete o grupo da última aplicação')).toBe('warning')
    expect(avaliacaoTom('grupo diferente do da última aplicação')).toBe('good')
  })
})
