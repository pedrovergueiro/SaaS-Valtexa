/**
 * Identificação da fazenda (brief, seção 5): produtor, CPF/CNPJ, município, UF,
 * cultura principal, CAR, responsável técnico e observações.
 *
 * O servidor confere CPF/CNPJ e CAR de novo (`services/documentos.py`); a
 * conferência aqui é para a pessoa ver o erro antes de salvar.
 */
import type { FarmOut } from '@/api/types'

export const REGISTRY_KEYS = [
  'owner_name',
  'owner_document',
  'city',
  'state',
  'main_crop',
  'car_code',
  'technical_lead',
  'notes',
] as const
export type RegistryKey = (typeof REGISTRY_KEYS)[number]
export type RegistryValues = Record<RegistryKey, string>

export function emptyRegistry(): RegistryValues {
  return Object.fromEntries(REGISTRY_KEYS.map((key) => [key, ''])) as RegistryValues
}

export function registryFromFarm(farm: FarmOut): RegistryValues {
  const valores = emptyRegistry()
  for (const key of REGISTRY_KEYS) {
    const atual = farm[key]
    valores[key] = key === 'owner_document' && atual ? formatDocument(atual) : (atual ?? '')
  }
  return valores
}

/** O corpo do cadastro: texto vazio vira `null`. */
export function registryPayload(values: RegistryValues): Record<RegistryKey, string | null> {
  return Object.fromEntries(REGISTRY_KEYS.map((key) => [key, values[key].trim() || null])) as Record<
    RegistryKey,
    string | null
  >
}

/** Só o que mudou, para o PATCH (e a auditoria) não registrar o que ficou igual. */
export function registryChanges(farm: FarmOut, values: RegistryValues): Partial<Record<RegistryKey, string | null>> {
  const corpo = registryPayload(values)
  const mudou: Partial<Record<RegistryKey, string | null>> = {}
  for (const key of REGISTRY_KEYS) {
    const antes = farm[key] ?? null
    const depois = key === 'owner_document' && corpo[key] ? corpo[key].replace(/\D/g, '') : corpo[key]
    const normalizado = key === 'state' && depois ? depois.toUpperCase() : depois
    if (normalizado !== antes) mudou[key] = corpo[key]
  }
  return mudou
}

const digitos = (texto: string) => texto.replace(/\D/g, '')

function dv(base: string, pesos: number[]): number {
  const resto = base.split('').reduce((soma, d, i) => soma + Number(d) * (pesos[i] ?? 0), 0) % 11
  return resto < 2 ? 0 : 11 - resto
}

export function validCpf(numeros: string): boolean {
  if (numeros.length !== 11 || /^(\d)\1+$/.test(numeros)) return false
  const d1 = dv(numeros.slice(0, 9), [10, 9, 8, 7, 6, 5, 4, 3, 2])
  const d2 = dv(numeros.slice(0, 10), [11, 10, 9, 8, 7, 6, 5, 4, 3, 2])
  return numeros.slice(9) === `${d1}${d2}`
}

export function validCnpj(numeros: string): boolean {
  if (numeros.length !== 14 || /^(\d)\1+$/.test(numeros)) return false
  const pesos = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
  const d1 = dv(numeros.slice(0, 12), pesos)
  const d2 = dv(numeros.slice(0, 13), [6, ...pesos])
  return numeros.slice(12) === `${d1}${d2}`
}

/** Mensagem do problema no CPF/CNPJ digitado, ou `null` se está bom (ou vazio). */
export function documentProblem(texto: string): string | null {
  const numeros = digitos(texto)
  if (!texto.trim()) return null
  if (numeros.length === 11) return validCpf(numeros) ? null : 'CPF inválido: confira os dígitos.'
  if (numeros.length === 14) return validCnpj(numeros) ? null : 'CNPJ inválido: confira os dígitos.'
  return 'Informe um CPF (11 dígitos) ou CNPJ (14 dígitos).'
}

const CAR = /^[A-Z]{2}-\d{7}-[0-9A-F]{32}$/

export function carProblem(texto: string): string | null {
  if (!texto.trim()) return null
  return CAR.test(texto.replace(/[\s.]/g, '').toUpperCase())
    ? null
    : 'Formato do recibo: UF-1234567-seguido de 32 caracteres.'
}

/** 52998224725 → 529.982.247-25; 11222333000181 → 11.222.333/0001-81. */
export function formatDocument(valor: string): string {
  const n = digitos(valor)
  if (n.length === 11) return `${n.slice(0, 3)}.${n.slice(3, 6)}.${n.slice(6, 9)}-${n.slice(9)}`
  if (n.length === 14) return `${n.slice(0, 2)}.${n.slice(2, 5)}.${n.slice(5, 8)}/${n.slice(8, 12)}-${n.slice(12)}`
  return valor
}

/** O que falta na identificação, na ordem em que vale a pena completar. */
export function farmRegistryGaps(farm: FarmOut): string[] {
  const falta: string[] = []
  if (!farm.owner_name) falta.push('produtor')
  if (!farm.owner_document) falta.push('CPF/CNPJ')
  if (!farm.city || !farm.state) falta.push('município/UF')
  if (!farm.car_code) falta.push('CAR')
  if (!farm.technical_lead) falta.push('responsável técnico')
  return falta
}
