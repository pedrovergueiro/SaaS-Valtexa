import { describe, expect, it } from 'vitest'

import { supportFormProblems } from './EnterAsClient'
import { PLATFORM_ROLES, platformRoleLabel, subscriptionLabel } from './labels'
import { TOOLS_WITH_TENANT, visibleNav } from './PlatformShell'

// As capacidades de cada papel, como o servidor as devolve em /v1/platform/me
// (saas/valtexa/security/rbac.py, PLATFORM_ROLE_CAPABILITIES).
const COMERCIAL = [
  'platform:tenant:read',
  'platform:tenant:manage',
  'platform:plan:read',
  'platform:plan:manage',
  'platform:usage:read',
]
const SUPORTE = [
  'platform:tenant:read',
  'platform:plan:read',
  'platform:usage:read',
  'platform:support:session',
  'platform:support:assist',
  'platform:audit:read',
  'platform:user:read',
  'platform:fleet:read',
  'platform:ticket:read',
  'platform:ticket:manage',
]
const IA_DADOS = [
  'platform:tenant:read',
  'platform:model:read',
  'platform:model:manage',
  'platform:model:release',
  'platform:fleet:read',
  'collection:manage',
  'dataset:read',
  'dataset:manage',
  'platform:ticket:read',
]
const OPERACOES = [
  'platform:ticket:read',
  'platform:tenant:read',
  'platform:field:operate',
  'platform:model:read',
  'platform:fleet:read',
]

const rotas = (caps: string[]) => visibleNav(caps).flatMap((grupo) => grupo.items.map((item) => item.to))

describe('menu do console da plataforma, pelo papel', () => {
  it('comercial vê clientes e cadastro, e não auditoria nem dados', () => {
    // Comercial não atende chamado; a central de notificações é de toda a equipe.
    expect(rotas(COMERCIAL)).toEqual([
      '/plataforma/clientes',
      '/plataforma/cadastro',
      '/plataforma/notificacoes',
      '/plataforma/saude',
    ])
  })

  it('suporte vê clientes, usuários, auditoria, a frota e as atualizações (diagnóstico)', () => {
    expect(rotas(SUPORTE)).toEqual([
      '/plataforma/clientes',
      '/plataforma/suporte',
      '/plataforma/notificacoes',
      '/plataforma/usuarios',
      '/plataforma/auditoria',
      '/plataforma/frota',
      '/plataforma/comando',
      '/plataforma/atualizacoes',
      '/plataforma/saude',
    ])
  })

  it('Operações vê frota, IA (leitura) e gerar missão', () => {
    expect(rotas(OPERACOES)).toEqual([
      '/plataforma/clientes',
      '/plataforma/suporte',
      '/plataforma/notificacoes',
      '/plataforma/frota',
      '/plataforma/comando',
      '/plataforma/ia',
      '/plataforma/atualizacoes',
      '/plataforma/planejamento',
      '/plataforma/saude',
    ])
  })

  it('IA & Dados vê frota, IA, coletas e dataset', () => {
    expect(rotas(IA_DADOS)).toEqual([
      '/plataforma/clientes',
      '/plataforma/suporte',
      '/plataforma/notificacoes',
      '/plataforma/frota',
      '/plataforma/comando',
      '/plataforma/ia',
      '/plataforma/atualizacoes',
      '/plataforma/coletas/nova',
      '/plataforma/coletas',
      '/plataforma/dataset',
      '/plataforma/saude',
    ])
  })

  it('papel de cliente não vê nada', () => {
    expect(rotas(['farm:read', 'audit:read', 'collection:read'])).toEqual([])
  })

  it('as ferramentas por cliente estão no menu', () => {
    const todas = rotas([...COMERCIAL, ...SUPORTE, ...IA_DADOS, 'platform:field:operate'])
    for (const prefixo of TOOLS_WITH_TENANT) expect(todas.some((rota) => rota.startsWith(prefixo))).toBe(true)
  })
})

describe('formulário de entrar como cliente', () => {
  const base = { reason: 'Chamado 42: talhão sumiu', minutes: 60, assisted: false, assistedReason: '' }

  it('aceita leitura com motivo', () => {
    expect(supportFormProblems(base)).toEqual([])
  })

  it('motivo é obrigatório', () => {
    expect(supportFormProblems({ ...base, reason: 'curto' })).toHaveLength(1)
  })

  it('assistido pede motivo próprio', () => {
    expect(supportFormProblems({ ...base, assisted: true })).toHaveLength(1)
    expect(supportFormProblems({ ...base, assisted: true, assistedReason: 'corrigir espaçamento' })).toEqual([])
  })

  it('prazo entre 5 min e 8 h, como o servidor', () => {
    expect(supportFormProblems({ ...base, minutes: 600 })).toHaveLength(1)
  })
})

describe('rótulos', () => {
  it('papéis e assinatura em português', () => {
    expect(PLATFORM_ROLES.map(platformRoleLabel)).toEqual(['Superadmin', 'Suporte', 'IA & Dados', 'Operações', 'Comercial'])
    expect(platformRoleLabel(null)).toBe('Sem papel de plataforma')
    expect(subscriptionLabel(null)).toBe('Sem plano')
    expect(subscriptionLabel('suspensa')).toBe('Suspensa')
  })
})
