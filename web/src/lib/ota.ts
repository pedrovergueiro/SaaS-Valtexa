/**
 * OTA no console interno (brief, seção 24): estados de cada robô e quanto falta.
 * O estado vem do que o robô informou; aqui só se mostra.
 */
import type { Tone } from './labels'

const ESTADO: Record<string, { label: string; tone: Tone }> = {
  pendente: { label: 'Pendente', tone: 'neutral' },
  baixando: { label: 'Baixando', tone: 'info' },
  verificando: { label: 'Conferindo assinatura e hash', tone: 'info' },
  instalando: { label: 'Instalando ao lado', tone: 'info' },
  verificando_saude: { label: 'Em teste', tone: 'warning' },
  aplicada: { label: 'Aplicada', tone: 'good' },
  revertida: { label: 'Revertida', tone: 'critical' },
  falhou: { label: 'Falhou', tone: 'critical' },
  recusada: { label: 'Recusada pelo robô', tone: 'critical' },
  cancelada: { label: 'Cancelada', tone: 'neutral' },
}

export const OTA_FINAIS = new Set(['aplicada', 'revertida', 'falhou', 'recusada', 'cancelada'])
export const otaStateLabel = (s: string): string => ESTADO[s]?.label ?? s
export const otaStateTone = (s: string): Tone => ESTADO[s]?.tone ?? 'neutral'
export const podeCancelar = (s: string): boolean => s === 'pendente' || s === 'baixando'

const TIPO: Record<string, string> = {
  runtime: 'Rover Runtime',
  edge_ai: 'Edge AI',
  model: 'Modelo',
  config: 'Configuração',
}
export const otaKindLabel = (k: string): string => TIPO[k] ?? k

/** Resumo de um lote de destinos: quantos em cada grupo (aplicada, em curso, problema). */
export function otaResumo(estados: string[]): { aplicadas: number; emCurso: number; problemas: number } {
  let aplicadas = 0
  let emCurso = 0
  let problemas = 0
  for (const s of estados) {
    if (s === 'aplicada') aplicadas += 1
    else if (s === 'revertida' || s === 'falhou' || s === 'recusada') problemas += 1
    else if (!OTA_FINAIS.has(s)) emCurso += 1
  }
  return { aplicadas, emCurso, problemas }
}
