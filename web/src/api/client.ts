/**
 * Cliente HTTP do console.
 *
 * Fala só com as rotas públicas de `/v1` — as mesmas que o simulador e qualquer
 * integração usam. Não existe rota privada de frontend, e nenhuma permissão é
 * decidida aqui: o servidor confere tudo de novo. Esconder um botão é
 * conveniência; o `403` é a resposta de verdade.
 */

export class ApiError extends Error {
  readonly status: number
  readonly detail: string

  constructor(status: number, detail: string) {
    super(detail)
    this.status = status
    this.detail = detail
  }
}

type Credentials = { token: string; tenantId: string | null }

let credentials: Credentials | null = null
let onUnauthorized: (() => void) | null = null

export function setCredentials(next: Credentials | null): void {
  credentials = next
}

export function setUnauthorizedHandler(handler: (() => void) | null): void {
  onUnauthorized = handler
}

export function authHeaders(): Record<string, string> {
  const headers: Record<string, string> = {}
  if (credentials) {
    headers.Authorization = `Bearer ${credentials.token}`
    if (credentials.tenantId) headers['X-Tenant-Id'] = credentials.tenantId
  }
  return headers
}

export type Query = Record<string, string | number | boolean | null | undefined>

type RequestOptions = {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
  body?: unknown
  query?: Query
  signal?: AbortSignal
}

export function buildUrl(path: string, query?: Query): string {
  const url = new URL(path, window.location.origin)
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined && value !== null && value !== '') url.searchParams.set(key, String(value))
  }
  return url.pathname + url.search
}

async function send(path: string, options: RequestOptions): Promise<Response> {
  const headers: Record<string, string> = authHeaders()
  if (options.body !== undefined) headers['Content-Type'] = 'application/json'

  const response = await fetch(buildUrl(path, options.query), {
    method: options.method ?? 'GET',
    headers,
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
    signal: options.signal,
  })

  if (response.status === 401 && credentials) onUnauthorized?.()
  if (!response.ok) throw new ApiError(response.status, await readDetail(response))
  return response
}

export async function api<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const response = await send(path, options)
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

/**
 * Envia um arquivo como corpo cru (pacote OTA): `fetch` com o `File` direto, sem
 * ler tudo para a memória do JavaScript. A resposta é JSON, como nas outras rotas.
 */
export async function apiUpload<T>(path: string, body: Blob, query: Query, contentType: string): Promise<T> {
  const headers: Record<string, string> = { ...authHeaders(), 'Content-Type': contentType }
  const response = await fetch(buildUrl(path, query), { method: 'POST', headers, body })
  if (response.status === 401 && credentials) onUnauthorized?.()
  if (!response.ok) throw new ApiError(response.status, await readDetail(response))
  return (await response.json()) as T
}

export async function apiBlob(path: string, signal?: AbortSignal): Promise<Blob> {
  const response = await send(path, { signal })
  return response.blob()
}

async function readDetail(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown }
    const detail = body.detail
    if (typeof detail === 'string') return detail
    // Erro de validação do FastAPI: lista de {loc, msg}.
    if (Array.isArray(detail)) {
      return detail
        .map((item) => {
          const entry = item as { loc?: unknown[]; msg?: string }
          const where = (entry.loc ?? []).filter((part) => part !== 'body').join('.')
          return where ? `${where}: ${entry.msg}` : entry.msg
        })
        .join('; ')
    }
    return JSON.stringify(detail)
  } catch {
    return response.statusText || `Erro ${response.status}`
  }
}
