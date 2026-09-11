import { useQuery, useQueryClient } from '@tanstack/react-query'
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'

import { api, setCredentials, setUnauthorizedHandler } from '@/api/client'
import { keys } from '@/api/queries'
import type { MeResponse, MembershipOut, TokenResponse } from '@/api/types'

/**
 * Sessão do console.
 *
 * Guarda só o token e o cliente escolhido. Papel e capacidades vêm sempre de
 * `/auth/me`, porque mudam por cliente e podem ser revogados a qualquer momento
 * — uma cópia no navegador ficaria desatualizada no pior momento possível.
 */

type StoredSession = {
  token: string
  tenantId: string | null
  email: string
  expiresAt: string
}

type AuthValue = {
  session: StoredSession | null
  me: MeResponse | undefined
  memberships: MembershipOut[]
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => void
  selectTenant: (tenantId: string) => void
  can: (capability: string) => boolean
}

const KEY = 'valtexa.session'
const AuthContext = createContext<AuthValue | null>(null)

function readSession(): StoredSession | null {
  try {
    const raw = localStorage.getItem(KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as StoredSession
    if (!parsed.token || new Date(parsed.expiresAt).getTime() <= Date.now()) return null
    return parsed
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

  useEffect(() => {
    setUnauthorizedHandler(logout)
    return () => setUnauthorizedHandler(null)
  }, [logout])

  // Sessão vencida enquanto a aba estava aberta.
  useEffect(() => {
    if (!session) return
    const remaining = new Date(session.expiresAt).getTime() - Date.now()
    const timer = window.setTimeout(logout, Math.max(0, remaining))
    return () => window.clearTimeout(timer)
  }, [session, logout])

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
    if (session && !session.tenantId && rows?.length === 1 && only) {
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
      })
    },
    [queryClient, update],
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
    }
  }, [session, me.data, me.isLoading, memberships.data, memberships.isLoading, login, logout, selectTenant])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth fora do AuthProvider')
  return value
}
