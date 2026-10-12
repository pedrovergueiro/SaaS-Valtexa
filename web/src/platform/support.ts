/**
 * "Entrar como cliente" no navegador: trocar de credencial sem perder a da equipe.
 *
 * A sessão de suporte devolve um token próprio, que vale só naquele cliente e
 * só até o prazo (brief, seção 29). O console guarda o token da equipe ao lado,
 * para voltar ao console da plataforma ao sair — ou quando a sessão de suporte
 * vence e o servidor responde 401: aí cai só o suporte, não o login inteiro.
 *
 * Funções puras sobre a sessão guardada: o `AuthProvider` aplica, os testes
 * conferem sem montar React.
 */

export type SupportInfo = {
  id: string
  tenantId: string
  tenantName: string
  mode: 'leitura' | 'assistido'
  reason: string
  expiresAt: string
  /** A credencial da equipe, para voltar ao console da plataforma. */
  platformToken: string
  platformTenantId: string | null
  platformExpiresAt: string
}

export type StoredSession = {
  token: string
  tenantId: string | null
  email: string
  expiresAt: string
  /** Pessoa da equipe ValTexa (o login devolveu capacidades `platform:*`). */
  platform?: boolean
  support?: SupportInfo
}

export type SupportStarted = {
  access_token: string
  expires_at: string
  tenant_id: string
  session: {
    id: string
    tenant_name?: string | null
    mode: 'leitura' | 'assistido'
    reason: string
  }
}

/** A sessão depois de entrar no cliente: o token ativo passa a ser o do suporte. */
export function enterSupport(session: StoredSession, started: SupportStarted): StoredSession {
  // Entrar de dentro de outra sessão de suporte volta à base da equipe primeiro:
  // nunca se empilha suporte sobre suporte.
  const base = session.support ? leaveSupport(session) : session
  return {
    ...base,
    token: started.access_token,
    tenantId: started.tenant_id,
    expiresAt: started.expires_at,
    support: {
      id: started.session.id,
      tenantId: started.tenant_id,
      tenantName: started.session.tenant_name ?? 'cliente',
      mode: started.session.mode,
      reason: started.session.reason,
      expiresAt: started.expires_at,
      platformToken: base.token,
      platformTenantId: base.tenantId,
      platformExpiresAt: base.expiresAt,
    },
  }
}

/** A sessão da equipe de volta, sem o suporte. */
export function leaveSupport(session: StoredSession): StoredSession {
  const support = session.support
  if (!support) return session
  return {
    token: support.platformToken,
    tenantId: support.platformTenantId,
    email: session.email,
    expiresAt: support.platformExpiresAt,
    platform: session.platform,
  }
}

/** Atualiza o modo mostrado na faixa depois de ligar ou desligar o assistido. */
export function withSupportMode(session: StoredSession, mode: SupportInfo['mode']): StoredSession {
  if (!session.support) return session
  return { ...session, support: { ...session.support, mode } }
}

/** Se a sessão guardada ainda vale: a da equipe pode sobreviver ao suporte vencido. */
export function restoreSession(stored: StoredSession | null, now = Date.now()): StoredSession | null {
  if (!stored?.token) return null
  if (stored.support && new Date(stored.support.expiresAt).getTime() <= now) {
    const base = leaveSupport(stored)
    return new Date(base.expiresAt).getTime() > now ? base : null
  }
  return new Date(stored.expiresAt).getTime() > now ? stored : null
}

/** Login devolveu alguma capacidade de plataforma? */
export function isPlatformLogin(capabilities: readonly string[]): boolean {
  return capabilities.some((cap) => cap.startsWith('platform:'))
}

/** Minutos que faltam, para a faixa. */
export function minutesLeft(expiresAt: string, now = Date.now()): number {
  return Math.max(0, Math.ceil((new Date(expiresAt).getTime() - now) / 60_000))
}
