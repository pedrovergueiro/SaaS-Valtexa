import { describe, expect, it } from 'vitest'

import {
  enterSupport,
  isPlatformLogin,
  leaveSupport,
  minutesLeft,
  restoreSession,
  withSupportMode,
  type StoredSession,
  type SupportStarted,
} from './support'

const AGORA = Date.parse('2026-10-03T12:00:00Z')

const equipe: StoredSession = {
  token: 'token-da-equipe',
  tenantId: null,
  email: 'suporte@valtexa.dev',
  expiresAt: '2026-10-03T20:00:00Z',
  platform: true,
}

const aberta: SupportStarted = {
  access_token: 'token-do-suporte',
  expires_at: '2026-10-03T14:00:00Z',
  tenant_id: 'cliente-a',
  session: { id: 'sup-1', tenant_name: 'Fazenda A', mode: 'leitura', reason: 'Chamado 42' },
}

describe('entrar como cliente', () => {
  it('troca a credencial ativa e guarda a da equipe', () => {
    const dentro = enterSupport(equipe, aberta)
    expect(dentro.token).toBe('token-do-suporte')
    expect(dentro.tenantId).toBe('cliente-a')
    expect(dentro.support?.platformToken).toBe('token-da-equipe')
    expect(dentro.support?.tenantName).toBe('Fazenda A')
    expect(dentro.support?.mode).toBe('leitura')
  })

  it('sair devolve exatamente a sessão da equipe', () => {
    expect(leaveSupport(enterSupport(equipe, aberta))).toEqual(equipe)
  })

  it('nunca empilha suporte sobre suporte', () => {
    const outra: SupportStarted = { ...aberta, access_token: 't2', tenant_id: 'cliente-b' }
    const segunda = enterSupport(enterSupport(equipe, aberta), outra)
    expect(segunda.support?.platformToken).toBe('token-da-equipe')
    expect(leaveSupport(segunda)).toEqual(equipe)
  })

  it('o modo assistido aparece na faixa', () => {
    expect(withSupportMode(enterSupport(equipe, aberta), 'assistido').support?.mode).toBe('assistido')
    expect(withSupportMode(equipe, 'assistido')).toBe(equipe)
  })
})

describe('restaurar ao recarregar a aba', () => {
  it('suporte vencido cai e a equipe continua', () => {
    const vencida = enterSupport(equipe, { ...aberta, expires_at: '2026-10-03T11:00:00Z' })
    expect(restoreSession(vencida, AGORA)).toEqual(equipe)
  })

  it('suporte vigente continua', () => {
    expect(restoreSession(enterSupport(equipe, aberta), AGORA)?.support?.id).toBe('sup-1')
  })

  it('login vencido não volta', () => {
    expect(restoreSession({ ...equipe, expiresAt: '2026-10-03T10:00:00Z' }, AGORA)).toBeNull()
    expect(restoreSession(null, AGORA)).toBeNull()
  })
})

describe('utilidades', () => {
  it('reconhece login da equipe pelas capacidades', () => {
    expect(isPlatformLogin(['platform:tenant:read'])).toBe(true)
    expect(isPlatformLogin(['farm:read', 'audit:read'])).toBe(false)
  })

  it('minutos restantes', () => {
    expect(minutesLeft('2026-10-03T12:30:00Z', AGORA)).toBe(30)
    expect(minutesLeft('2026-10-03T11:00:00Z', AGORA)).toBe(0)
  })
})
