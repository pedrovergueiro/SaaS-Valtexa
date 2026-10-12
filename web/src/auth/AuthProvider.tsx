import { useQuery, useQueryClient } from '@tanstack/react-query'
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'

import { api, setCredentials, setUnauthorizedHandler } from '@/api/client'
import { keys } from '@/api/queries'
import type { MeResponse, MembershipOut, TokenResponse } from '@/api/types'
import {
  enterSupport as enterSupportState,
  isPlatformLogin,
  leaveSupport,
  restoreSession,
  withSupportMode,
  type StoredSession,
  type SupportInfo,
  type SupportStarted,
} from '@/platform/support'

/**
 * Sessão do console.
 *
 * Guarda só o token e o cliente escolhido. Papel e capacidades vêm sempre de
 * `/auth/me`, porque mudam por cliente e podem ser revogados a qualquer momento
 * — uma cópia no navegador ficaria desatualizada no pior momento possível.
 */

type AuthValue = {
  session: StoredSession | null
  me: MeResponse | undefined
  memberships: MembershipOut[]
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => void
  selectTenant: (tenantId: string) => void
  can: (capability: string) => boolean
  /** Pessoa da equipe ValTexa (tem acesso ao console da plataforma). */
  isPlatform: boolean
  /** Sessão de suporte ativa ("entrar como cliente"), se houver. */
  support: SupportInfo | null
  enterSupport: (started: SupportStarted) => void
  exitSupport: () => Promise<void>
  setSupportMode: (mode: SupportInfo['mode']) => void
}

const KEY = 'valtexa.session'
const AuthContext = createContext<AuthValue | null>(null)

function readSession(): StoredSession | null {
  try {
    const raw = localStorage.getItem(KEY)
    if (!raw) return null
    return restoreSession(JSON.parse(raw) as StoredSession)
  } catch {
    return null
  }
}

function writeSession(session: StoredSession | null): void {
  try {
    if (session) localStorage.setItem(KEY, JSON.stringify(session))
    else localStorage.removeItem(KEY)
  } catch {
    // armazenamento bloqueado: a sessão vale até fechar a aba
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  const [session, setSession] = useState<StoredSession | null>(() => {
    const initial = readSession()
    setCredentials(initial ? { token: initial.token, tenantId: initial.tenantId } : null)
    return initial
  })

  const update = useCallback((next: StoredSession | null) => {
    setCredentials(next ? { token: next.token, tenantId: next.tenantId } : null)
    writeSession(next)
    setSession(next)
  }, [])

  const logout = useCallback(() => {
    update(null)
    queryClient.clear()
  }, [queryClient, update])

  /**
   * Volta ao console da plataforma sem chamar o servidor: a sessão de suporte
   * venceu ou foi encerrada por outra pessoa (o servidor já respondeu 401).
   */
  const dropSupport = useCallback(() => {
    if (!session?.support) return logout()
    queryClient.clear()
    update(leaveSupport(session))
  }, [logout, queryClient, session, update])

  useEffect(() => {
    setUnauthorizedHandler(session?.support ? dropSupport : logout)
    return () => setUnauthorizedHandler(null)
  }, [logout, dropSupport, session?.support])

  // Sessão vencida enquanto a aba estava aberta. Com suporte, vence só ele.
  useEffect(() => {
    if (!session) return
    const remaining = new Date(session.expiresAt).getTime() - Date.now()
    const timer = window.setTimeout(session.support ? dropSupport : logout, Math.max(0, remaining))
    return () => window.clearTimeout(timer)
  }, [session, logout, dropSupport])

  const memberships = useQuery({
    queryKey: keys.memberships,
    queryFn: () => api<MembershipOut[]>('/v1/auth/memberships'),
    enabled: Boolean(session),
    staleTime: 5 * 60_000,
  })

  const me = useQuery({
    queryKey: keys.me(session?.tenantId ?? null),
    queryFn: () => api<MeResponse>('/v1/auth/me'),
    enabled: Boolean(session?.tenantId),
    staleTime: 60_000,
  })

  // Um cliente só: entra direto, sem perguntar.
  useEffect(() => {
    const rows = memberships.data
    const only = rows?.[0]
    // A equipe não entra sozinha num cliente: a porta dela é o console da
    // plataforma, e o cliente se abre por "Entrar como cliente".
    if (session && !session.platform && !session.tenantId && rows?.length === 1 && only) {
      update({ ...session, tenantId: only.tenant_id })
    }
  }, [memberships.data, session, update])

  const login = useCallback(
    async (email: string, password: string) => {
      setCredentials(null)
      const token = await api<TokenResponse>('/v1/auth/login', {
        method: 'POST',
        body: { email, password },
      })
      queryClient.clear()
      update({
        token: token.access_token,
        tenantId: token.tenant_id ?? null,
        email,
        expiresAt: token.expires_at,
        platform: isPlatformLogin(token.capabilities ?? []),
      })
    },
    [queryClient, update],
  )

  const enterSupport = useCallback(
    (started: SupportStarted) => {
      if (!session) return
      queryClient.clear()
      update(enterSupportState(session, started))
    },
    [queryClient, session, update],
  )

  const exitSupport = useCallback(async () => {
    if (!session?.support) return
    try {
      // Com o token do suporte ainda ativo: a rota aceita o dono da sessão.
      await api(`/v1/platform/support-sessions/${session.support.id}/end`, {
        method: 'POST',
        body: { reason: 'saiu' },
      })
    } catch {
      // Já encerrada ou vencida: o servidor não aceita mais o token, e sair
      // localmente é exatamente o que se quer.
    }
    queryClient.clear()
    update(leaveSupport(session))
  }, [queryClient, session, update])

  const setSupportMode = useCallback(
    (mode: SupportInfo['mode']) => {
      if (!session) return
      queryClient.invalidateQueries()
      update(withSupportMode(session, mode))
    },
    [queryClient, session, update],
  )

  const selectTenant = useCallback(
    (tenantId: string) => {
      if (!session) return
      // Trocar de cliente troca papel e dados: nada do cache anterior serve.
      queryClient.clear()
      update({ ...session, tenantId })
    },
    [queryClient, session, update],
  )

  const value = useMemo<AuthValue>(() => {
    const capabilities = new Set(me.data?.capabilities ?? [])
    return {
      session,
      me: me.data,
      memberships: memberships.data ?? [],
      loading: Boolean(session) && (memberships.isLoading || (Boolean(session?.tenantId) && me.isLoading)),
      login,
      logout,
      selectTenant,
      can: (capability: string) => capabilities.has(capability),
      isPlatform: Boolean(session?.platform || me.data?.platform_role),
      support: session?.support ?? null,
      enterSupport,
      exitSupport,
      setSupportMode,
    }
  }, [
    session,
    me.data,
    me.isLoading,
    memberships.data,
    memberships.isLoading,
    login,
    logout,
    selectTenant,
    enterSupport,
    exitSupport,
    setSupportMode,
  ])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth fora do AuthProvider')
  return value
}
