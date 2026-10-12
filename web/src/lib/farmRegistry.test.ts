import { describe, expect, it } from 'vitest'

import type { FarmOut } from '@/api/types'

import {
  carProblem,
  documentProblem,
  emptyRegistry,
  farmRegistryGaps,
  formatDocument,
  registryChanges,
  registryFromFarm,
  registryPayload,
} from './farmRegistry'

const fazenda = (over: Partial<FarmOut> = {}): FarmOut => ({
  id: 'f1',
  name: 'Boa Vista',
  timezone: 'America/Sao_Paulo',
  center_lat: -12.5,
  center_lon: -55.7,
  base_lat: null,
  base_lon: null,
  area_ha: null,
  owner_name: null,
  owner_document: null,
  owner_document_masked: false,
  city: null,
  state: null,
  main_crop: null,
  car_code: null,
  technical_lead: null,
  notes: null,
  fields: 0,
  ...over,
})

describe('CPF, CNPJ e CAR', () => {
  it('aceita documento válido, com ou sem pontuação', () => {
    expect(documentProblem('529.982.247-25')).toBeNull()
    expect(documentProblem('11222333000181')).toBeNull()
    expect(documentProblem('')).toBeNull()
  })

  it('recusa dígito errado, repetição e tamanho', () => {
    expect(documentProblem('529.982.247-26')).toMatch(/CPF inválido/)
    expect(documentProblem('111.111.111-11')).toMatch(/CPF inválido/)
    expect(documentProblem('11.222.333/0001-80')).toMatch(/CNPJ inválido/)
    expect(documentProblem('123')).toMatch(/11 dígitos/)
  })

  it('CAR no formato do recibo', () => {
    expect(carProblem('mt-5107925-0123.4567.89ab.cdef.0123.4567.89ab.cdef')).toBeNull()
    expect(carProblem('MT-5107925-0123')).toMatch(/Formato/)
  })

  it('mostra o documento com a máscara', () => {
    expect(formatDocument('52998224725')).toBe('529.982.247-25')
    expect(formatDocument('11222333000181')).toBe('11.222.333/0001-81')
  })
})

describe('cadastro da fazenda', () => {
  it('vazio vira nulo no corpo', () => {
    const corpo = registryPayload({ ...emptyRegistry(), owner_name: '  Maria  ' })
    expect(corpo.owner_name).toBe('Maria')
    expect(corpo.car_code).toBeNull()
  })

  it('a edição manda só o que mudou, ignorando máscara e caixa', () => {
    const antes = fazenda({ owner_document: '52998224725', state: 'MT', owner_name: 'Maria' })
    const valores = registryFromFarm(antes)
    expect(valores.owner_document).toBe('529.982.247-25')
    expect(registryChanges(antes, { ...valores, state: 'mt' })).toEqual({})
    expect(registryChanges(antes, { ...valores, owner_name: 'Ana', car_code: '' })).toEqual({ owner_name: 'Ana' })
    expect(registryChanges(antes, { ...valores, owner_name: '' })).toEqual({ owner_name: null })
  })

  it('lista o que falta na identificação', () => {
    expect(farmRegistryGaps(fazenda())).toEqual(['produtor', 'CPF/CNPJ', 'município/UF', 'CAR', 'responsável técnico'])
    expect(
      farmRegistryGaps(
        fazenda({
          owner_name: 'Maria',
          owner_document: '52998224725',
          city: 'Sorriso',
          state: 'MT',
          car_code: 'MT-5107925-0123456789ABCDEF0123456789ABCDEF',
          technical_lead: 'Ana',
        }),
      ),
    ).toEqual([])
  })
})
