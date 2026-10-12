import { describe, expect, it } from 'vitest'

import {
  clientActions,
  historyLine,
  priorityTone,
  queueOrder,
  ticketStatusLabel,
  ticketStatusTone,
  waitingMinutes,
} from './support'

describe('chamados no console', () => {
  it('o cliente lê "aguardando você"; a equipe, "aguardando cliente"', () => {
    expect(ticketStatusLabel('aguardando_cliente', 'cliente')).toBe('Aguardando você')
    expect(ticketStatusLabel('aguardando_cliente')).toBe('Aguardando cliente')
    expect(ticketStatusTone('resolvido')).toBe('good')
    expect(priorityTone('urgente')).toBe('critical')
  })

  it('ações do cliente por situação', () => {
    expect(clientActions('aberto')).toEqual({ comment: true, close: true, reopen: false })
    expect(clientActions('resolvido')).toEqual({ comment: true, close: true, reopen: true })
    expect(clientActions('fechado')).toEqual({ comment: false, close: false, reopen: true })
  })

  it('linhas do histórico', () => {
    expect(historyLine({ kind: 'status', old_value: 'aberto', new_value: 'resolvido' })).toBe(
      'mudou a situação: Aberto → Resolvido',
    )
    expect(historyLine({ kind: 'prioridade', old_value: 'normal', new_value: 'urgente' })).toBe(
      'mudou a prioridade: Normal → Urgente',
    )
    expect(historyLine({ kind: 'incidente', old_value: null, new_value: 'INC-0001' })).toBe(
      'incidente: — → INC-0001',
    )
    expect(historyLine({ kind: 'sessao_suporte', new_value: 'leitura' })).toContain('sessão de suporte')
    expect(historyLine({ kind: 'comentario' })).toBe('comentou')
  })

  it('espera pela primeira resposta', () => {
    const agora = new Date('2026-10-04T12:00:00Z')
    expect(waitingMinutes({ created_at: '2026-10-04T10:30:00Z' }, agora)).toBe(90)
    expect(waitingMinutes({ created_at: '2026-10-04T10:30:00Z', first_response_at: '2026-10-04T11:00:00Z' }, agora)).toBeNull()
  })

  it('fila: abertos, urgentes e mais antigos primeiro', () => {
    const fila = queueOrder([
      { id: 'fechado-urgente', priority: 'urgente', status: 'fechado', last_activity_at: '2026-10-01' },
      { id: 'normal-velho', priority: 'normal', status: 'aberto', last_activity_at: '2026-10-01' },
      { id: 'alta', priority: 'alta', status: 'em_atendimento', last_activity_at: '2026-10-03' },
      { id: 'urgente', priority: 'urgente', status: 'aberto', last_activity_at: '2026-10-04' },
      { id: 'normal-novo', priority: 'normal', status: 'aberto', last_activity_at: '2026-10-02' },
    ])
    expect(fila.map((t) => t.id)).toEqual(['urgente', 'alta', 'normal-velho', 'normal-novo', 'fechado-urgente'])
  })
})
