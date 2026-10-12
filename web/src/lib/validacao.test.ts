import { describe, expect, it } from 'vitest'

import {
  afrouxa,
  camposDoEnsaio,
  converteParametro,
  criterioTexto,
  portaoInfo,
  progressoTexto,
  rotuloFase,
  situacaoItem,
  statusEnsaio,
} from './validacao'

describe('ensaios', () => {
  it('critério como o operador lê', () => {
    expect(criterioTexto({ nome: 'x', valor: 12.5, limite: 20, op: '<=', unidade: 'mm', ok: true })).toBe('12,5 mm ≤ 20')
    expect(criterioTexto({ nome: 'x', valor: null, limite: 1, op: '>=', unidade: '', ok: false })).toBe('— ≥ 1')
  })

  it('formulário: conversão e aviso de limite frouxo', () => {
    expect(converteParametro('', 5)).toBeUndefined()
    expect(converteParametro('0,3', 5)).toBe(0.3)
    expect(converteParametro('sim', false)).toBe(true)
    expect(converteParametro('0.4, 0.4 0.2;0.2', [0.4, 0.4, 0.2, 0.2])).toEqual([0.4, 0.4, 0.2, 0.2])
    expect(converteParametro('oak-0', null)).toBe('oak-0')
    expect(converteParametro('500', null)).toBe(500)
    expect(afrouxa(30, 20, 'max')).toBe(true)
    expect(afrouxa(10, 20, 'max')).toBe(false)
    expect(afrouxa(100, 256, 'min')).toBe(true)
    expect(afrouxa(100, null, 'max')).toBe(false)
  })

  it('campos do catálogo: livres e limites', () => {
    const campos = camposDoEnsaio({
      nome: 'profundidade', fase: 0, titulo: '', origem: 'rover', no_portao: true,
      limites: { tolerancia_mm: { padrao: 20, sentido: 'max' } },
      parametros: { camera_id: null, distancia_real_mm: null },
      obrigatorios: ['camera_id', 'distancia_real_mm'],
    })
    expect(campos.map((c) => c.nome)).toEqual(['camera_id', 'distancia_real_mm', 'tolerancia_mm'])
    expect(campos[0]?.obrigatorio).toBe(true)
    expect(campos[2]?.limite).toBe('max')
  })

  it('situações e portão', () => {
    expect(statusEnsaio('aprovado').tone).toBe('good')
    expect(statusEnsaio('nao_avaliado').label).toBe('Não avaliado')
    expect(situacaoItem('so_simulado').label).toBe('Só simulado')
    expect(portaoInfo({ fase: 2, titulo: '', automatico: false, aprovado: null, itens: [], informativos: [] }).label).toBe('Manual (guia)')
    expect(portaoInfo({ fase: 0, titulo: '', automatico: true, aprovado: false, itens: [], informativos: [] }).tone).toBe('critical')
    expect(progressoTexto({ fracao: 0.426 })).toBe('43 %')
    expect(progressoTexto(null)).toBe('')
  })
})

describe('fase ENLACE', () => {
  it('mostra ENLACE no lugar do número 6', () => {
    expect(rotuloFase(6)).toBe('ENLACE')
    expect(rotuloFase(1)).toBe('1')
  })
})
