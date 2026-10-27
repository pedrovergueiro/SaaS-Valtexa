import type { Tone } from '@/lib/labels'

/** Parecer do cérebro agronômico (rodada 4, 8.2), como a API devolve. */
export interface ItemDossie {
  id: string
  tipo: string
  titulo: string
  disponivel: boolean
  motivo_indisponivel: string | null
  origem: Record<string, unknown>
  versao_modelo: string | null
  dados: Record<string, unknown>
  limitacoes: string[]
}

export interface Afirmacao {
  id: string
  secao: string
  texto: string
  citacoes: string[]
}

export interface Verificacao {
  codigo: string
  titulo: string
  situacao: 'a_verificar' | 'sem_fonte' | 'bloqueado' | 'sem_dado'
  detalhe: string
  citacoes: string[]
}

export interface FonteCitada {
  id: string
  documento_id: string
  titulo: string
  versao: string
  tipo: string
  origem: string
  licenca: string
  secao: string | null
  texto: string
  sha256_trecho: string
  uso_operacional: boolean
  bloqueio: string | null
  ficticio: boolean
  regulatorio: boolean
}

export interface Revisao {
  id: string
  revisor_id: string
  papel: string
  decisao: 'concorda' | 'discorda' | 'inconclusivo'
  comentario: string | null
  diagnostico_revisor: string | null
  revisado_em: string
}

export interface ParecerResumo {
  id: string
  field_id: string
  caso_tipo: 'planta' | 'observacao'
  plant_ref: string | null
  observation_id: string | null
  modo: 'deterministico' | 'provedor'
  provedor: string | null
  estado: 'aguardando_revisao' | 'revisado'
  gerado_em: string
  hipotese_principal: string | null
  alternativas: string[]
  fontes: number
  recusas: number
  pendencias: number
}

export interface Parecer extends Omit<ParecerResumo, 'fontes' | 'recusas'> {
  texto: string
  afirmacoes: Afirmacao[]
  verificacoes: Verificacao[]
  fecho: string
  fontes: FonteCitada[]
  /** A situação de HOJE de cada fonte citada (o parecer guarda a do dia em que foi gerado). */
  fontes_hoje?: FonteHoje[] | null
  dossie: { itens: ItemDossie[]; hipoteses: { principal: string | null; alternativas: { classe: string; evidencias: string[] }[] } }
  recusas: { origem: string; erro?: string; recusas?: { motivos: string[]; texto?: string }[] }[]
  revisoes: Revisao[]
  integro: boolean
  sha256: string
  aviso: string
}

export interface FonteHoje {
  id: string
  documento_id: string | null
  existe: boolean
  estado?: string
  substituido_por?: string | null
  uso_operacional: boolean
  bloqueio: string | null
  mudou: boolean
}

/** O aviso de que a fonte mudou desde o parecer (venceu, foi substituída, saiu do repositório). */
export function avisoDeHoje(h: FonteHoje | undefined): string | null {
  if (!h || !h.mudou) return null
  if (!h.existe) return 'Hoje: fora do repositório'
  if (h.estado && h.estado !== 'vigente') return `Hoje: ${h.estado} por versão mais nova`
  return h.uso_operacional ? 'Hoje: liberada para uso operacional' : `Hoje: ${h.bloqueio ?? 'bloqueada'}`
}

export const SECOES: Record<string, string> = {
  caso: 'Caso',
  hipoteses: 'Hipóteses',
  evidencia: 'Evidência',
  limitacoes: 'Limitações',
  historico: 'Histórico',
  risco: 'Risco (gêmeo digital)',
  clima: 'Clima',
  licoes: 'O que o agrônomo ensinou',
  regras_agronomo: 'Regras dos agrônomos',
  fontes: 'Fontes',
  regras: 'Regras determinísticas',
  texto: 'Texto',
}

/** Afirmações agrupadas por seção, na ordem em que o compositor as escreveu. */
export function porSecao(afirmacoes: Afirmacao[]): { secao: string; titulo: string; itens: Afirmacao[] }[] {
  const grupos: { secao: string; titulo: string; itens: Afirmacao[] }[] = []
  for (const a of afirmacoes) {
    let g = grupos.find((x) => x.secao === a.secao)
    if (!g) {
      g = { secao: a.secao, titulo: SECOES[a.secao] ?? a.secao, itens: [] }
      grupos.push(g)
    }
    g.itens.push(a)
  }
  return grupos
}

const SITUACAO: Record<Verificacao['situacao'], { texto: string; tom: Tone }> = {
  a_verificar: { texto: 'A verificar pelo responsável', tom: 'warning' },
  sem_fonte: { texto: 'Sem fonte', tom: 'neutral' },
  bloqueado: { texto: 'Bloqueado (fonte vencida ou não verificada)', tom: 'critical' },
  sem_dado: { texto: 'Sem dado', tom: 'neutral' },
}

export function situacaoTexto(s: Verificacao['situacao']): string {
  return SITUACAO[s]?.texto ?? s
}

export function situacaoTom(s: Verificacao['situacao']): Tone {
  return SITUACAO[s]?.tom ?? 'neutral'
}

export function decisaoTexto(d: Revisao['decisao']): string {
  return { concorda: 'Concorda', discorda: 'Discorda', inconclusivo: 'Pede mais evidência' }[d] ?? d
}

/** O que cada citação aponta: item do dossiê (E) ou trecho de fonte (F). */
export function alvoDaCitacao(p: Pick<Parecer, 'dossie' | 'fontes'>, citacao: string): string {
  if (citacao.startsWith('E')) {
    const item = p.dossie.itens.find((i) => i.id === citacao)
    return item ? `${citacao} · ${item.titulo}` : `${citacao} · (não está no dossiê)`
  }
  const f = p.fontes.find((x) => x.id === citacao)
  return f ? `${citacao} · ${f.titulo} v${f.versao}` : `${citacao} · (não está nas fontes)`
}

/** Selo da fonte: fictícia, bloqueada, regulatória vigente ou técnica. */
export function seloDaFonte(f: FonteCitada): { texto: string; tom: Tone } {
  if (f.ficticio) return { texto: 'Fictícia (teste)', tom: 'critical' }
  if (f.regulatorio && !f.uso_operacional) return { texto: `Bloqueada: ${f.bloqueio}`, tom: 'critical' }
  if (f.regulatorio) return { texto: 'Regulatória verificada', tom: 'good' }
  return { texto: 'Técnica (não embasa dose nem registro)', tom: 'info' }
}

export function modoTexto(p: Pick<ParecerResumo, 'modo' | 'provedor'>): string {
  return p.modo === 'provedor' ? `Texto do provedor ${p.provedor}, validado` : 'Compositor determinístico'
}
