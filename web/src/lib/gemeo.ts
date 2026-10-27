/**
 * Gêmeo digital do talhão (VALTEXA-B, `app.gemeo`) no console: os tipos das respostas da IA,
 * repassadas pela plataforma, e o que a tela decide a partir delas.
 */
import type { Tone } from '@/lib/labels'

export type Atualidade = {
  ultimo_dia_observado: string | null
  dias_sem_observacao: number | null
  desatualizada: boolean
}

export type ResumoClima = {
  dias: number
  inicio: string | null
  fim: string | null
  por_fonte: Record<string, number>
  atualidade?: Atualidade
}

export type Gemeo = {
  plantas: number
  ruas: number
  doencas: string[]
  passadas: { pass_id: string; dia: number; fonte: string; plantas_vistas: number }[]
  clima: ResumoClima
  modelos: Record<string, { ajustado_em: string | null; passadas: string[] | null; diagnostico: { identificado?: boolean; motivo?: string } } | null>
}

export type Nota = { modelo: number | null; persistencia: number | null; prevalencia: number | null }

export type ErroDoTempo = {
  fonte: string
  dias_a_frente: string
  n: number
  erro_medio: { t_media: number; ur_media: number; chuva_mm: number; molhamento_h: number }
}

export type RegistroDeModo = {
  modo: 'observacao' | 'ativo'
  desde: string | null
  responsavel: string | null
  motivo: string | null
  historico?: RegistroDeModo[]
}

export type Avaliacao = {
  doenca: string
  passadas_avaliadas: number
  plantas: number
  nota_por_planta: Nota
  por_passada: ({ pass_id: string; plantas: number } & Nota)[]
  passadas_do_ajuste: number
  pode_ativar: boolean
  motivos: string[]
  parametros: string
  clima: string
  tempo_previsto: { comparados: number; por_fonte_e_antecedencia: ErroDoTempo[] }
  modo: RegistroDeModo
}

export type Previsao = {
  data_base: string
  hoje: string
  horizonte: string
  parametros_ajustados: boolean
  esporulando_agora_esperado: number
  infectadas_no_horizonte_esperado: number
  infectadas_no_horizonte_p10_p90: [number, number] | null
  janelas_de_infeccao: { inicio: string; fim: string; dias: number; favorabilidade_max: number }[]
  focos_agora: number
  focos_no_horizonte: number
  focos_novos_no_horizonte: number
  avisos: string[]
}

export const FONTE_DO_CLIMA: Record<string, string> = {
  estacao: 'estação da fazenda',
  'open-meteo:historico': 'reanálise (Open-Meteo)',
  'open-meteo:previsao': 'previsão do tempo',
  climatologia: 'climatologia',
}

/** O que o modo quer dizer para quem vai aprovar um mapa. */
export function modoTexto(modo: RegistroDeModo['modo']): { rotulo: string; tom: Tone; explica: string } {
  return modo === 'ativo'
    ? { rotulo: 'ativo', tom: 'good', explica: 'O mapa de aplicação feito pelo gêmeo sai como proposta (ainda passa pela sua aprovação e pelo Safety Engine).' }
    : { rotulo: 'em observação', tom: 'warning', explica: 'O gêmeo prevê, mas o mapa feito por ele é registro para comparar — o Safety Engine não o executa.' }
}

/** Quem prevê melhor nas passadas avaliadas (maior nota = melhor; zero = a passada não disse nada). */
export function quemVence(nota: Nota): 'modelo' | 'persistencia' | 'prevalencia' | null {
  const candidatos = (['modelo', 'persistencia', 'prevalencia'] as const).filter((k) => nota[k] != null)
  if (candidatos.length === 0) return null
  return candidatos.reduce((melhor, k) => ((nota[k] as number) > (nota[melhor] as number) ? k : melhor))
}

/** O erro de molhamento é o que mais pesa: acima de 3 h, a janela de infecção pode mudar de dia. */
export function tomDoErroDeMolhamento(horas: number): Tone {
  return horas > 3 ? 'critical' : horas > 1.5 ? 'warning' : 'good'
}
