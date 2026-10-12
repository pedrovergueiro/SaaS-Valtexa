import { describe, expect, it } from 'vitest'

import {
  badgeCount,
  deliverySummary,
  groupByDay,
  notificationTone,
  preferenceBody,
  preferenceSource,
} from './notifications'

describe('notificações no console', () => {
  it('a entrega diz a verdade sobre o e-mail', () => {
    expect(deliverySummary({ channel: 'email', status: 'enviado', last_error: null })).toEqual({
      text: 'E-mail: enviado',
      tone: 'good',
    })
    const semSmtp = deliverySummary({
      channel: 'email',
      status: 'nao_enviado',
      last_error: 'SMTP não configurado (SMTP_HOST vazio): o aviso ficou só na central.',
    })
    expect(semSmtp.text).toBe(
      'E-mail: não enviado — SMTP não configurado (SMTP_HOST vazio): o aviso ficou só na central.',
    )
    expect(semSmtp.tone).toBe('warning')
    expect(deliverySummary({ channel: 'email', status: 'desistiu', last_error: 'recusado' }).tone).toBe('critical')
    expect(deliverySummary({ channel: 'email', status: 'pendente', last_error: 'x' }).text).toBe('E-mail: na fila')
  })

  it('número do sino', () => {
    expect(badgeCount(0)).toBeNull()
    expect(badgeCount(7)).toBe('7')
    expect(badgeCount(140)).toBe('99+')
  })

  it('tons por severidade', () => {
    expect(notificationTone('critico')).toBe('critical')
    expect(notificationTone('aviso')).toBe('warning')
    expect(notificationTone('qualquer')).toBe('neutral')
  })

  it('agrupa por dia mantendo a ordem', () => {
    const itens = [
      { id: 'a', created_at: '2026-10-04T15:00:00Z' },
      { id: 'b', created_at: '2026-10-04T09:00:00Z' },
      { id: 'c', created_at: '2026-10-03T20:00:00Z' },
    ]
    const grupos = groupByDay(itens, (iso) => iso.slice(0, 10))
    expect(grupos.map((g) => [g.day, g.items.map((i) => i.id)])).toEqual([
      ['2026-10-04', ['a', 'b']],
      ['2026-10-03', ['c']],
    ])
  })

  it('corpo da preferência: desligado não leva e-mail; limite só quando o tipo tem', () => {
    expect(preferenceBody('rover_offline', { enabled: true, email: true, threshold: 9 }, false)).toEqual({
      kind: 'rover_offline',
      enabled: true,
      channels: ['email'],
      threshold: null,
    })
    expect(preferenceBody('incidencia_alta', { enabled: false, email: true, threshold: 12 }, true)).toEqual({
      kind: 'incidencia_alta',
      enabled: false,
      channels: [],
      threshold: 12,
    })
    expect(preferenceSource('papel')).toContain('gestor')
  })
})
