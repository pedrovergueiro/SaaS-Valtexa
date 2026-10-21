/**
 * Orçamento de dados pela Starlink do robô (rodada 4): o que o próprio Rover contou e o que
 * a plataforma recebeu. Ver `saas/valtexa/services/orcamento_dados.py`.
 */
import type { Tone } from '@/lib/labels'

export interface DadosContados {
  dia: string | null
  usado_bytes: number | null
  enviados_bytes: number | null
  recebidos_bytes: number | null
  teto_dia_bytes: number | null
  fracao_usada: number | null
  origem_do_teto: 'plataforma' | 'rover.json' | null
  prioridade_maxima_liberada: number | null
  adiados: number | null
  retidos: number | null
  tempestade: boolean
  por_classe: Record<string, number | null>
}

export interface DiaMedido {
  dia: string
  arquivos_bytes: number
  arquivos: number
  arquivos_deduplicados: number
  registros_bytes: number
  registros: number
  eventos: number
  telemetria_amostras: number
  total_bytes: number
  por_papel: Record<string, number>
}

export interface Aviso {
  tipo: 'EVENT_STORM' | 'DATA_BUDGET' | string
  em: string
  severidade: string | null
  missao: string | null
  dados: Record<string, unknown>
}

export interface RelatorioDados {
  device_id: string
  nome: string
  teto: { bytes_dia: number | null; bytes_missao: number | null; origem: string; efetivo_dia_bytes: number | null }
  contado_no_rover: DadosContados | null
  contado_em: string | null
  medido_na_plataforma: DiaMedido[]
  fracao_hoje: number | null
  recebido_hoje_bytes: number
  avisos: Aviso[]
  nota: string
}

const UNIDADES = ['B', 'kB', 'MB', 'GB', 'TB']

/** Bytes em unidades decimais (como a Starlink cobra): 1 GB = 10⁹ bytes. */
export function bytesText(valor: number | null | undefined): string {
  if (valor == null || Number.isNaN(valor)) return 'sem dado'
  let v = Math.max(0, valor)
  let i = 0
  while (v >= 1000 && i < UNIDADES.length - 1) {
    v /= 1000
    i += 1
  }
  const casas = i === 0 ? 0 : v < 10 ? 2 : v < 100 ? 1 : 0
  return `${v.toLocaleString('pt-BR', { minimumFractionDigits: casas, maximumFractionDigits: casas })} ${UNIDADES[i]}`
}

export function fracaoTone(fracao: number | null | undefined, tempestade = false): Tone {
  if (tempestade) return 'serious'
  if (fracao == null) return 'neutral'
  if (fracao >= 1) return 'critical'
  if (fracao >= 0.8) return 'warning'
  return 'good'
}

const PRIORIDADES: Record<number, string> = {
  1: 'só o que nunca corta (comando, segurança, telemetria, eventos)',
  2: 'até doença/praga',
  3: 'até anomalia',
  4: 'até conclusão de missão',
  5: 'até imagens normais reduzidas',
  6: 'tudo',
}

export function prioridadeText(p: number | null | undefined): string {
  if (p == null) return 'sem dado'
  return PRIORIDADES[p] ?? `prioridade ${p}`
}

const CLASSES: Record<string, string> = {
  arquivos: 'Imagens',
  registros: 'Resultados e eventos',
  telemetria: 'Telemetria',
  comando: 'Comandos',
  missao: 'Missão',
  atualizacao: 'Atualizações',
  video: 'Vídeo ao vivo',
  outros: 'Outros',
}

/** As classes do dia, da maior para a menor, com o rótulo do console. */
export function classesOrdenadas(porClasse: Record<string, number | null> | undefined): { classe: string; rotulo: string; bytes: number }[] {
  return Object.entries(porClasse ?? {})
    .filter((e): e is [string, number] => typeof e[1] === 'number')
    .map(([classe, bytes]) => ({ classe, rotulo: CLASSES[classe] ?? classe, bytes }))
    .sort((a, b) => b.bytes - a.bytes)
}

export function avisoText(a: Aviso): string {
  if (a.tipo === 'EVENT_STORM') {
    const taxa = typeof a.dados.taxa_eventos === 'number' ? ` (${Math.round(a.dados.taxa_eventos * 100)}% dos quadros)` : ''
    return a.dados.estado === 'fim' ? 'Tempestade de eventos acabou' : `Tempestade de eventos${taxa}: originais retidos no disco`
  }
  if (a.tipo === 'DATA_BUDGET') {
    const nivel = typeof a.dados.nivel === 'number' ? Math.round(a.dados.nivel * 100) : null
    return nivel != null ? `Usou ${nivel}% do teto do dia` : 'Teto do dia'
  }
  return a.tipo
}
