/**
 * Formulários do console da plataforma que antes só existiam na API (Parte 8):
 *
 * - **publicar pacote OTA** (`POST /v1/platform/ota/packages`, corpo = o `.tar`) e
 *   **destinar** (`POST /v1/platform/ota/deployments`);
 * - **registrar rodada de otimização dNATY**
 *   (`POST /v1/platform/models/{id}/optimizations`, corpo = o relatório de
 *   `ia/training/dnaty_pipeline.py`).
 *
 * As regras de verdade estão no servidor (modelo só em PRODUÇÃO, hash do artefato
 * dentro do pacote, critério do dNATY recalculado). Aqui só se monta o pedido e se
 * avisa antes o que o servidor recusaria de qualquer jeito.
 */

export const OTA_KINDS = ['runtime', 'edge_ai', 'model', 'config'] as const
export type OtaKind = (typeof OTA_KINDS)[number]

export type RegistryVersion = {
  id: string
  model_key: string
  version: string
  state: string
  original_artifact_sha256?: string | null
  optimized_artifact_sha256?: string | null
}

/** O artefato que o robô recebe (o otimizado, se houver) e o nome que ele precisa ter no `.tar`. */
export function robotArtifact(v: RegistryVersion): { sha256: string; kind: 'otimizado' | 'original'; file: string } | null {
  if (v.optimized_artifact_sha256) {
    return { sha256: v.optimized_artifact_sha256, kind: 'otimizado', file: `${v.optimized_artifact_sha256}.onnx` }
  }
  if (v.original_artifact_sha256) {
    return { sha256: v.original_artifact_sha256, kind: 'original', file: `${v.original_artifact_sha256}.onnx` }
  }
  return null
}

/** Só versões em PRODUÇÃO e com artefato com hash podem virar pacote de modelo. */
export const publishableVersions = (versions: RegistryVersion[]) =>
  versions.filter((v) => v.state === 'producao' && robotArtifact(v) !== null)

export type OtaPublishForm = {
  kind: OtaKind | ''
  version: string
  modelVersionId: string
  notes: string
  file: { name: string; size: number } | null
}

export const MAX_OTA_BYTES = 512 * 1024 * 1024

export function otaPublishErrors(form: OtaPublishForm): string[] {
  const erros: string[] = []
  if (!form.kind) erros.push('Escolha o tipo do pacote.')
  if (!form.version.trim()) erros.push('Informe a versão do pacote.')
  else if (form.version.trim().length > 64) erros.push('Versão com no máximo 64 caracteres.')
  if (form.kind === 'model' && !form.modelVersionId) erros.push('Pacote de modelo precisa da versão do registry (em PRODUÇÃO).')
  if (!form.file) erros.push('Escolha o arquivo .tar do pacote.')
  else {
    if (!form.file.name.toLowerCase().endsWith('.tar')) erros.push('O pacote é um arquivo .tar.')
    if (form.file.size > MAX_OTA_BYTES) erros.push('Pacote acima de 512 MB.')
    if (form.file.size === 0) erros.push('Arquivo vazio.')
  }
  return erros
}

/** Os parâmetros de consulta do `POST /v1/platform/ota/packages`. */
export function otaPublishQuery(form: OtaPublishForm): Record<string, string> {
  const q: Record<string, string> = { kind: form.kind, version: form.version.trim() }
  if (form.kind === 'model' && form.modelVersionId) q.model_version_id = form.modelVersionId
  if (form.notes.trim()) q.notes = form.notes.trim().slice(0, 1000)
  return q
}

export type OtaTarget = { mode: 'cliente'; tenantId: string } | { mode: 'robos'; deviceIds: string[] }

export function otaDeploymentBody(packageId: string, target: OtaTarget): Record<string, unknown> {
  return target.mode === 'cliente'
    ? { package_id: packageId, tenant_id: target.tenantId }
    : { package_id: packageId, device_ids: target.deviceIds }
}

export function otaTargetErrors(target: OtaTarget): string[] {
  if (target.mode === 'cliente') return target.tenantId ? [] : ['Escolha o cliente.']
  if (!target.deviceIds.length) return ['Escolha ao menos um robô.']
  if (target.deviceIds.length > 1000) return ['No máximo 1000 robôs por vez.']
  return []
}

// --- dNATY -------------------------------------------------------------------------

export const BENCHMARK_REQUIRED = ['precision', 'recall', 'f1', 'latency_ms_p50', 'size_bytes', 'sha256'] as const

type Benchmark = Record<string, unknown>
type Lado = { path?: string; artifact_uri?: string | null; benchmark?: Benchmark }

export type DnatyParse = {
  ok: boolean
  errors: string[]
  /** O corpo para a API, sem os `artifact_uri` (a tela pede). */
  body: {
    tool: string
    tool_version: string | null
    dnaty_version: string | null
    parametros: Record<string, unknown>
    criterio: Record<string, unknown> | null
    original: { artifact_uri: string | null; benchmark: Benchmark }
    otimizado: { artifact_uri: string | null; benchmark: Benchmark }
  } | null
  /** Onde os arquivos estavam na máquina do treino (só para orientar quem preenche a URI). */
  paths: { original: string | null; otimizado: string | null }
  /** O veredito que o relatório trazia: o registry ignora e recalcula. */
  reportVerdict: boolean | null
}

const text = (v: unknown) => (typeof v === 'string' && v.trim() ? v.trim() : null)

/** Lê o JSON do `dnaty_pipeline.py` e diz o que falta antes de mandar. */
export function parseDnatyReport(raw: string): DnatyParse {
  const vazio: DnatyParse = { ok: false, errors: [], body: null, paths: { original: null, otimizado: null }, reportVerdict: null }
  let dados: Record<string, unknown>
  try {
    const lido = JSON.parse(raw) as unknown
    if (!lido || typeof lido !== 'object' || Array.isArray(lido)) return { ...vazio, errors: ['O arquivo não é um objeto JSON.'] }
    dados = lido as Record<string, unknown>
  } catch {
    return { ...vazio, errors: ['O arquivo não é JSON válido.'] }
  }
  const erros: string[] = []
  const tool = text(dados.tool)
  if (!tool) erros.push('Relatório sem "tool".')
  const lados = { original: dados.original as Lado | undefined, otimizado: dados.otimizado as Lado | undefined }
  for (const [nome, lado] of Object.entries(lados)) {
    if (!lado || typeof lado !== 'object' || !lado.benchmark || typeof lado.benchmark !== 'object') {
      erros.push(`Relatório sem "${nome}.benchmark".`)
      continue
    }
    const faltam = BENCHMARK_REQUIRED.filter((k) => lado.benchmark?.[k] == null)
    if (faltam.length) erros.push(`Benchmark do ${nome} sem ${faltam.join(', ')}.`)
  }
  const shaO = lados.original?.benchmark?.sha256
  const shaT = lados.otimizado?.benchmark?.sha256
  if (shaO && shaT && shaO === shaT) erros.push('Otimizado e original são o mesmo arquivo (mesmo SHA-256).')
  const body = erros.length
    ? null
    : {
        tool: tool!,
        tool_version: text(dados.tool_version),
        dnaty_version: text(dados.dnaty_version),
        parametros: (dados.parametros as Record<string, unknown>) ?? {},
        criterio: (dados.criterio as Record<string, unknown> | undefined) ?? null,
        original: { artifact_uri: text(lados.original?.artifact_uri), benchmark: lados.original!.benchmark! },
        otimizado: { artifact_uri: text(lados.otimizado?.artifact_uri), benchmark: lados.otimizado!.benchmark! },
      }
  return {
    ok: erros.length === 0,
    errors: erros,
    body,
    paths: { original: text(lados.original?.path), otimizado: text(lados.otimizado?.path) },
    reportVerdict: typeof dados.aceito === 'boolean' ? dados.aceito : null,
  }
}

/** Monta o corpo final com as URIs que a pessoa informou. */
export function dnatyBody(
  parsed: DnatyParse,
  uris: { original: string; otimizado: string },
): DnatyParse['body'] {
  if (!parsed.body) return null
  return {
    ...parsed.body,
    original: { ...parsed.body.original, artifact_uri: uris.original.trim() || parsed.body.original.artifact_uri },
    otimizado: { ...parsed.body.otimizado, artifact_uri: uris.otimizado.trim() || parsed.body.otimizado.artifact_uri },
  }
}

/** Antes da aprovação: a otimização entra em TREINAMENTO ou VALIDAÇÃO. */
export const canOptimize = (state: string) => state === 'treinamento' || state === 'validacao'
