import { describe, expect, it } from 'vitest'

import {
  consentSummary,
  featureLabel,
  planSituation,
  supportModeLabel,
  supportSessionStatus,
  usageAlerts,
  usageText,
  type ConsentStatus,
  type MyPlan,
  type TenantSupportSession,
  type UsageItem,
} from './account'

const item = (resource: string, used: number, limit: number | null): UsageItem => ({
  resource,
  label: resource,
  used,
  limit,
  percent: limit ? Math.round((1000 * used) / limit) / 10 : null,
})

describe('uso do plano', () => {
  it('avisa a partir de 80 %, do mais apertado para o menos', () => {
    const alertas = usageAlerts([item('fazendas', 1, 10), item('talhoes', 8, 10), item('robos', 2, 2)])
    expect(alertas.map((a) => [a.resource, a.tone])).toEqual([
      ['robos', 'critical'],
      ['talhoes', 'warning'],
    ])
    expect(alertas[0]?.text).toMatch(/limite do plano atingido/)
    expect(alertas[1]?.text).toMatch(/80 %/)
  })

  it('recurso sem limite nunca vira aviso', () => {
    expect(usageAlerts([item('hectares', 5000, null)])).toEqual([])
    expect(usageText(item('hectares', 12.5, null))).toBe('12,5 (sem limite)')
    expect(usageText(item('talhoes', 3, 10))).toBe('3 de 10')
  })
})

describe('situação do plano', () => {
  const base = {
    tenant_id: 't',
    plan: null,
    started_at: null,
    ends_at: null,
    overrides: {},
    notes: null,
    effective_limits: {},
    usage: [],
  }
  it('sem assinatura diz que não há plano', () => {
    expect(planSituation({ ...base, has_subscription: false, status: null } as MyPlan).label).toBe(
      'Sem plano contratado',
    )
  })
  it('suspensa aparece como crítica', () => {
    expect(planSituation({ ...base, has_subscription: true, status: 'suspensa' } as MyPlan)).toEqual({
      label: 'Suspensa',
      tone: 'critical',
    })
  })
  it('recursos em português', () => {
    expect(featureLabel('lavoura_3d')).toBe('Lavoura 3D')
    expect(featureLabel('novo')).toBe('novo')
  })
})

describe('dados no treino', () => {
  const status = (decided: boolean, allowed: boolean): ConsentStatus => ({
    tenant_id: 't',
    decided,
    allowed,
    current: null,
    history: [],
  })
  it('sem decisão vale NÃO', () => {
    expect(consentSummary(status(false, false))).toMatch(/vale NÃO/)
  })
  it('SIM e NÃO explícitos', () => {
    expect(consentSummary(status(true, true))).toMatch(/^SIM/)
    expect(consentSummary(status(true, false))).toMatch(/^NÃO/)
  })
})

describe('entradas da ValTexa', () => {
  const sessao = (over: Partial<TenantSupportSession>): TenantSupportSession => ({
    id: 's',
    tenant_id: 't',
    user_id: 'u',
    reason: 'Chamado 7',
    ticket_ref: null,
    mode: 'leitura',
    assisted_reason: null,
    started_at: '2026-10-03T10:00:00Z',
    expires_at: '2026-10-03T11:00:00Z',
    ended_at: null,
    ended_reason: null,
    request_count: 3,
    is_open: false,
    ...over,
  })
  it('diz se está em andamento, venceu ou a equipe saiu', () => {
    expect(supportSessionStatus(sessao({ is_open: true }))).toBe('Em andamento')
    expect(supportSessionStatus(sessao({ ended_reason: 'expirou' }))).toBe('Encerrada pelo prazo')
    expect(supportSessionStatus(sessao({ ended_reason: 'saiu' }))).toBe('Encerrada pela equipe')
    expect(supportSessionStatus(sessao({ ended_reason: 'encerrada por x: y' }))).toBe('Encerrada: encerrada por x: y')
  })
  it('modo em português', () => {
    expect(supportModeLabel('leitura')).toBe('Somente leitura')
    expect(supportModeLabel('assistido')).toMatch(/Assistido/)
  })
})
