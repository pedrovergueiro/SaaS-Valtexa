import { describe, expect, it } from 'vitest'

import { fieldSetupGaps, formatValidationRows, optionalNumber, parseValidationRows } from './fieldSetup'

describe('fileiras de validação', () => {
  it('lê números e faixas, em ordem e sem repetição', () => {
    expect(parseValidationRows('10, 3-5; 4 12')).toEqual({ rows: [3, 4, 5, 10, 12], error: null })
  })

  it('vazio é lista vazia', () => {
    expect(parseValidationRows('  ')).toEqual({ rows: [], error: null })
  })

  it('recusa linha zero, faixa invertida e texto', () => {
    expect(parseValidationRows('0').error).toMatch(/começa em 1/)
    expect(parseValidationRows('5-3').error).toMatch(/Faixa inválida/)
    expect(parseValidationRows('a, 2').error).toMatch(/Não entendi/)
  })

  it('recusa fileira além do número de linhas', () => {
    expect(parseValidationRows('3, 41', 40).error).toMatch(/40 linhas/)
    expect(parseValidationRows('3, 40', 40).error).toBeNull()
  })

  it('escreve de volta compactando sequências', () => {
    expect(formatValidationRows([9, 3, 4, 5])).toBe('3-5, 9')
    expect(formatValidationRows([])).toBe('')
    expect(parseValidationRows(formatValidationRows([1, 2, 7, 8, 9, 20])).rows).toEqual([1, 2, 7, 8, 9, 20])
  })
})

describe('número opcional', () => {
  it('aceita vírgula decimal e trata vazio como nulo', () => {
    expect(optionalNumber('2,5')).toBe(2.5)
    expect(optionalNumber('')).toBeNull()
    expect(optionalNumber('abc')).toBeNull()
  })
})

describe('o que falta no cadastro do talhão', () => {
  const completo = {
    boundary: [[0, 0], [1, 0], [1, 1]],
    row_spacing_m: 3.5,
    plant_spacing_m: 2.5,
    row_azimuth_deg: 0,
    row_count: 40,
    validation_rows: [3, 10],
  }

  it('talhão completo não pede nada (direção 0 vale)', () => {
    expect(fieldSetupGaps(completo)).toEqual([])
  })

  it('cada falta vem com a próxima ação', () => {
    const faltas = fieldSetupGaps({ ...completo, plant_spacing_m: null, validation_rows: [] })
    expect(faltas.map((f) => f.key)).toEqual(['espacamento', 'validacao'])
    expect(faltas.every((f) => f.action.length > 0)).toBe(true)
  })

  it('sem contorno é a primeira coisa', () => {
    expect(fieldSetupGaps({ ...completo, boundary: [] })[0]?.key).toBe('contorno')
  })
})
