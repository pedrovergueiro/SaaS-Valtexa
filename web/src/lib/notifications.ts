/**
 * Notificações no console (brief, seção 48): rótulos e regras de exibição.
 *
 * O servidor decide quem recebe o quê; aqui só se traduz o estado — em especial
 * o da entrega por e-mail, que precisa dizer a verdade: "não enviado (SMTP não
 * configurado)" não pode aparecer como "enviado".
 */
import type { Tone } from './labels'

export type DeliveryLike = { channel: string; status: string; last_error?: string | null }
export type NotificationLike = { severity: string; read_at?: string | null; deliveries: DeliveryLike[] }

const SEVERITY_TONE: Record<string, Tone> = { info: 'info', aviso: 'warning', critico: 'critical' }
const SEVERITY_LABEL: Record<string, string> = { info: 'Informação', aviso: 'Atenção', critico: 'Crítico' }

export const notificationTone = (severity: string): Tone => SEVERITY_TONE[severity] ?? 'neutral'
export const notificationSeverity = (severity: string) => SEVERITY_LABEL[severity] ?? severity

const CHANNEL_LABEL: Record<string, string> = {
  in_app: 'Central',
  email: 'E-mail',
  whatsapp: 'WhatsApp',
  push: 'Push',
  sms: 'SMS',
}
export const channelLabel = (name: string) => CHANNEL_LABEL[name] ?? name

const DELIVERY: Record<string, { label: string; tone: Tone }> = {
  pendente: { label: 'na fila', tone: 'neutral' },
  enviado: { label: 'enviado', tone: 'good' },
  nao_enviado: { label: 'não enviado', tone: 'warning' },
  falhou: { label: 'falhou, vai tentar de novo', tone: 'warning' },
  desistiu: { label: 'não entregue', tone: 'critical' },
}

/** "E-mail: enviado", "E-mail: não enviado — SMTP não configurado...". */
export function deliverySummary(delivery: DeliveryLike): { text: string; tone: Tone } {
  const info = DELIVERY[delivery.status] ?? { label: delivery.status, tone: 'neutral' as Tone }
  const motivo =
    delivery.status === 'enviado' || delivery.status === 'pendente' || !delivery.last_error
      ? ''
      : ` — ${delivery.last_error}`
  return { text: `${channelLabel(delivery.channel)}: ${info.label}${motivo}`, tone: info.tone }
}

/** Número do sino: 99+ não cabe. */
export function badgeCount(unread: number): string | null {
  if (!unread || unread < 0) return null
  return unread > 99 ? '99+' : String(unread)
}

/** Separa por dia, mantendo a ordem do servidor (mais novo primeiro). */
export function groupByDay<T extends { created_at: string }>(
  items: T[],
  dayOf: (iso: string) => string,
): { day: string; items: T[] }[] {
  const grupos: { day: string; items: T[] }[] = []
  for (const item of items) {
    const dia = dayOf(item.created_at)
    const ultimo = grupos[grupos.length - 1]
    if (ultimo && ultimo.day === dia) ultimo.items.push(item)
    else grupos.push({ day: dia, items: [item] })
  }
  return grupos
}

export type PreferenceDraft = { enabled: boolean; email: boolean; threshold: number | null }

/** O corpo do PUT a partir do que a pessoa marcou na tela. */
export function preferenceBody(kind: string, draft: PreferenceDraft, hasThreshold: boolean) {
  return {
    kind,
    enabled: draft.enabled,
    channels: draft.enabled && draft.email ? ['email'] : [],
    threshold: hasThreshold ? draft.threshold : null,
  }
}

const SOURCE_LABEL: Record<string, string> = {
  pessoa: 'sua escolha',
  papel: 'definido pelo gestor para o seu papel',
  padrao: 'padrão da ValTexa',
}
export const preferenceSource = (source: string) => SOURCE_LABEL[source] ?? source
