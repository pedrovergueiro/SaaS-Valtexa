/**
 * O que o console do cliente mostra sobre a própria conta: plano e uso, uso dos
 * dados no treino e as entradas da equipe ValTexa (brief, seções 29, 31 e 32).
 *
 * Funções puras, para o vitest conferir as regras sem montar tela.
 */
import type { components } from '@/api/schema'

type S = components['schemas']
export type MyPlan = S['SubscriptionOut']
export type UsageItem = S['UsageItem']
export type ConsentStatus = S['DataConsentStatus']
export type TenantSupportSession = S['SupportSessionOut']

/** A partir daqui o uso vira aviso; o servidor usa o mesmo número (plans_api). */
export const AVISO_PERCENTUAL = 80

export type UsageAlert = { resource: string; label: string; tone: 'warning' | 'critical'; text: string }

/** Itens perto (≥ 80 %) ou no limite (≥ 100 %), do mais apertado para o menos. */
export function usageAlerts(usage: readonly UsageItem[]): UsageAlert[] {
  return usage
    .filter((item) => item.percent !== null && item.percent !== undefined && item.percent >= AVISO_PERCENTUAL)
    .sort((a, b) => (b.percent ?? 0) - (a.percent ?? 0))
    .map((item) => {
      const cheio = (item.percent ?? 0) >= 100
      return {
        resource: item.resource,
        label: item.label,
        tone: cheio ? 'critical' : 'warning',
        text: cheio
          ? `${item.label}: limite do plano atingido. Novos cadastros serão recusados até ampliar o plano.`
          : `${item.label}: ${Math.round(item.percent ?? 0)} % do limite do plano.`,
      }
    })
}

/** "3 de 10", "3 (sem limite)" — o texto do uso de cada recurso. */
export function usageText(item: UsageItem): string {
  const usado = Number.isInteger(item.used) ? String(item.used) : item.used.toFixed(1).replace('.', ',')
  if (item.limit === null || item.limit === undefined) return `${usado} (sem limite)`
  const limite = Number.isInteger(item.limit) ? String(item.limit) : item.limit.toFixed(1).replace('.', ',')
  return `${usado} de ${limite}`
}

const RECURSOS: Record<string, string> = {
  prescricao: 'Prescrição',
  lavoura_3d: 'Lavoura 3D',
  validacao_campo: 'Validação em campo',
  relatorios: 'Relatórios',
}

export function featureLabel(code: string): string {
  return RECURSOS[code] ?? code
}

const SITUACAO: Record<string, string> = {
  teste: 'Em teste',
  ativa: 'Ativa',
  suspensa: 'Suspensa',
  cancelada: 'Cancelada',
}

export function planSituation(plan: MyPlan): { label: string; tone: 'good' | 'info' | 'critical' | 'neutral' } {
  if (!plan.has_subscription || !plan.status) return { label: 'Sem plano contratado', tone: 'neutral' }
  const label = SITUACAO[plan.status] ?? plan.status
  if (plan.status === 'ativa') return { label, tone: 'good' }
  if (plan.status === 'teste') return { label, tone: 'info' }
  return { label, tone: 'critical' }
}

/** De onde veio a decisão sobre os dados no treino. */
export function consentSourceLabel(source: string): string {
  if (source === 'cliente') return 'Decidido aqui no console'
  if (source === 'contrato') return 'Registrado pela ValTexa a partir de termo assinado'
  return source
}

/** A frase que resume o consentimento vigente. Sem decisão, vale NÃO (seção 32). */
export function consentSummary(status: ConsentStatus): string {
  if (!status.decided) {
    return 'Ninguém decidiu ainda, então vale NÃO: nenhuma imagem desta conta entra no treino dos modelos.'
  }
  return status.allowed
    ? 'SIM: as imagens desta conta podem ser usadas para melhorar os modelos da ValTexa.'
    : 'NÃO: nenhuma imagem desta conta entra no treino dos modelos.'
}

/** Situação de uma entrada da equipe ValTexa, como o cliente lê. */
export function supportSessionStatus(sessao: TenantSupportSession): string {
  if (sessao.is_open) return 'Em andamento'
  if (sessao.ended_reason === 'expirou') return 'Encerrada pelo prazo'
  if (sessao.ended_reason === 'saiu') return 'Encerrada pela equipe'
  return sessao.ended_reason ? `Encerrada: ${sessao.ended_reason}` : 'Encerrada'
}

export function supportModeLabel(mode: string): string {
  return mode === 'assistido' ? 'Assistido (pode alterar)' : 'Somente leitura'
}
