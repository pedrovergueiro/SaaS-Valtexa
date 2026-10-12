/**
 * Notificações e chamados (Parte 6): as mesmas operações no console do cliente
 * e no da plataforma, mudando só a raiz da rota. O servidor decide a caixa (a
 * pessoa no cliente ativo, ou a equipe); aqui não se filtra nada.
 */
import { useQuery } from '@tanstack/react-query'

import { api, type Query } from './client'
import { useApiMutation } from './queries'
import type * as T from './types'

export type Audience = 'cliente' | 'plataforma'

/** Campos com padrão no servidor são opcionais aqui (só ``kind`` é obrigatório). */
export type PreferenceBody = Partial<T.NotificationPreferenceIn> & { kind: string }

const raiz = (audience: Audience) => (audience === 'cliente' ? '/v1/notifications' : '/v1/platform/notifications')

export const supportKeys = {
  notifications: (audience: Audience) => ['notifications', audience] as const,
  unread: (audience: Audience) => ['notifications', audience, 'unread'] as const,
  list: (audience: Audience, query: Query) => ['notifications', audience, 'list', query] as const,
  prefs: (audience: Audience) => ['notifications', audience, 'prefs'] as const,
  rolePrefs: (audience: Audience, role: string) => ['notifications', audience, 'role-prefs', role] as const,
  tickets: (audience: Audience, query: Query = {}) => ['tickets', audience, query] as const,
  ticket: (audience: Audience, id: string) => ['tickets', audience, 'one', id] as const,
  incidents: (query: Query = {}) => ['incidents', query] as const,
  incident: (id: string) => ['incidents', 'one', id] as const,
}

// --- notificações -----------------------------------------------------------------

export const useUnreadCount = (audience: Audience, enabled = true) =>
  useQuery({
    queryKey: supportKeys.unread(audience),
    queryFn: () => api<{ unread: number }>(`${raiz(audience)}/unread-count`),
    enabled,
    refetchInterval: 30_000,
  })

export const useNotifications = (audience: Audience, query: Query = {}, enabled = true) =>
  useQuery({
    queryKey: supportKeys.list(audience, query),
    queryFn: () => api<T.NotificationOut[]>(raiz(audience), { query }),
    enabled,
  })

export function useMarkRead(audience: Audience) {
  return useApiMutation(
    (id: string) => api<T.NotificationOut>(`${raiz(audience)}/${id}/read`, { method: 'POST' }),
    [supportKeys.notifications(audience)],
  )
}

export function useMarkAllRead(audience: Audience) {
  return useApiMutation(
    () => api<{ marked: number }>(`${raiz(audience)}/read-all`, { method: 'POST' }),
    [supportKeys.notifications(audience)],
  )
}

export const useMyPreferences = (audience: Audience) =>
  useQuery({
    queryKey: supportKeys.prefs(audience),
    queryFn: () => api<T.NotificationPreferencesOut>(`${raiz(audience)}/preferences`),
  })

export function useSetMyPreference(audience: Audience) {
  return useApiMutation(
    (body: PreferenceBody) =>
      api<T.NotificationPreferencesOut>(`${raiz(audience)}/preferences`, { method: 'PUT', body }),
    [supportKeys.prefs(audience)],
  )
}

export const useRolePreferences = (audience: Audience, role: string, enabled = true) =>
  useQuery({
    queryKey: supportKeys.rolePrefs(audience, role),
    queryFn: () => api<T.NotificationPreferencesOut>(`${raiz(audience)}/role-preferences`, { query: { role } }),
    enabled: enabled && Boolean(role),
  })

export function useSetRolePreference(audience: Audience) {
  return useApiMutation(
    (body: PreferenceBody & { role: string }) =>
      api<T.NotificationPreferencesOut>(`${raiz(audience)}/role-preferences`, { method: 'PUT', body }),
    [['notifications', audience]],
  )
}

// --- chamados -----------------------------------------------------------------------

const ticketRoot = (audience: Audience) => (audience === 'cliente' ? '/v1/support/tickets' : '/v1/platform/tickets')

export const useTickets = (audience: Audience, query: Query = {}) =>
  useQuery({
    queryKey: supportKeys.tickets(audience, query),
    queryFn: () => api<T.TicketOut[]>(ticketRoot(audience), { query }),
    refetchInterval: 60_000,
  })

export const useTicket = (audience: Audience, id: string) =>
  useQuery({
    queryKey: supportKeys.ticket(audience, id),
    queryFn: () => api<T.TicketDetailOut>(`${ticketRoot(audience)}/${id}`),
    enabled: Boolean(id),
    refetchInterval: 30_000,
  })

export function useOpenTicket(audience: Audience) {
  return useApiMutation(
    (body: T.TicketCreate & { tenant_id?: string }) =>
      api<T.TicketDetailOut>(ticketRoot(audience), { method: 'POST', body }),
    [['tickets', audience]],
  )
}

export function useCommentTicket(audience: Audience, id: string) {
  return useApiMutation(
    (body: { body: string; internal?: boolean }) =>
      api<T.TicketDetailOut>(`${ticketRoot(audience)}/${id}/comments`, { method: 'POST', body }),
    [['tickets', audience]],
  )
}

export function useClientTicketAction(id: string) {
  return useApiMutation(
    ({ action, reason }: { action: 'close' | 'reopen'; reason?: string }) =>
      api<T.TicketDetailOut>(`/v1/support/tickets/${id}/${action}`, {
        method: 'POST',
        body: { reason: reason ?? null },
      }),
    [['tickets', 'cliente']],
  )
}

export function useUpdateTicket(id: string) {
  return useApiMutation(
    (body: Partial<T.TicketUpdate>) =>
      api<T.TicketDetailOut>(`/v1/platform/tickets/${id}`, { method: 'PATCH', body }),
    [['tickets', 'plataforma'], ['incidents']],
  )
}

// --- incidentes (só a equipe) --------------------------------------------------------

export const useIncidents = (query: Query = {}) =>
  useQuery({
    queryKey: supportKeys.incidents(query),
    queryFn: () => api<T.IncidentOut[]>('/v1/platform/incidents', { query }),
  })

export const useIncident = (id: string | null) =>
  useQuery({
    queryKey: supportKeys.incident(id ?? ''),
    queryFn: () => api<T.IncidentDetailOut>(`/v1/platform/incidents/${id}`),
    enabled: Boolean(id),
  })

export function useCreateIncident() {
  return useApiMutation(
    (body: { title: string; description?: string; severity: string; public_note?: string | null; ticket_ids: string[] }) =>
      api<T.IncidentDetailOut>('/v1/platform/incidents', { method: 'POST', body }),
    [['incidents'], ['tickets', 'plataforma']],
  )
}

export function useUpdateIncident(id: string) {
  return useApiMutation(
    (body: { status?: string; severity?: string; public_note?: string | null; title?: string }) =>
      api<T.IncidentDetailOut>(`/v1/platform/incidents/${id}`, { method: 'PATCH', body }),
    [['incidents'], ['tickets', 'plataforma']],
  )
}

export const useAssignees = () =>
  useQuery({
    queryKey: ['tickets', 'assignees'],
    queryFn: () => api<T.TicketAssigneeOut[]>('/v1/platform/support/assignees'),
    staleTime: 5 * 60_000,
  })
