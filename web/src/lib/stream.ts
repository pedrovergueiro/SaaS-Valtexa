/**
 * Eventos da plataforma em tempo real (SSE), lidos com `fetch`.
 *
 * `EventSource` do navegador não aceita cabeçalho de autorização, então o
 * stream é lido à mão. Cada evento invalida as consultas afetadas — a tela se
 * atualiza sozinha sem polling agressivo — e os eventos que exigem atenção
 * viram aviso.
 *
 * A conexão tem prazo no servidor; ao terminar, reconecta de onde parou. Em
 * falha, recua exponencialmente até 30 s.
 */
import { useQueryClient, type QueryKey } from '@tanstack/react-query'
import { useEffect, useState } from 'react'

import { authHeaders, buildUrl } from '@/api/client'
import { keys } from '@/api/queries'
import { useAuth } from '@/auth/AuthProvider'
import { useToast } from '@/components/ui'
import { eventName, type Tone } from '@/lib/labels'

export type StreamStatus = 'off' | 'connecting' | 'live' | 'retrying'

type StreamEvent = { name: string; data: string }
type Payload = {
  id: string
  name: string
  subject_type: string | null
  subject_id: string | null
  payload: Record<string, unknown>
  created_at: string
}

const INVALIDATE: [prefix: string, keys: QueryKey[]][] = [
  ['mission.', [['missions'], keys.dashboard, keys.alerts, ['devices'], ['scene']]],
  ['safety.', [['missions'], keys.alerts]],
  ['diagnosis.', [keys.reviewQueue, ['observations'], ['twin'], keys.dashboard, ['scene']]],
  // Cada rua que o rover termina aparece na cópia 3D sem recarregar a página.
  ['row_scan.', [['scene']]],
  ['novelty.', [keys.reviewQueue, keys.alerts]],
  ['decision.', [['decisions']]],
  ['application.', [['applications'], keys.alerts, ['tanks'], keys.dashboard]],
  ['verification.', [keys.verifications, keys.alerts]],
  ['device.', [['devices'], keys.alerts, keys.dashboard]],
]

const NOTIFY: Record<string, Tone> = {
  'application.out_of_bounds': 'critical',
  'device.fault': 'critical',
  'safety.blocked': 'warning',
  'device.offline': 'warning',
  'mission.completed': 'good',
  'novelty.detected': 'info',
}

function parse(block: string): StreamEvent | null {
  let name = 'message'
  const data: string[] = []
  for (const line of block.split('\n')) {
    if (line.startsWith(':')) continue
    if (line.startsWith('event:')) name = line.slice(6).trim()
    else if (line.startsWith('data:')) data.push(line.slice(5).trimStart())
  }
  return data.length ? { name, data: data.join('\n') } : null
}

const sleep = (ms: number, signal: AbortSignal) =>
  new Promise<void>((resolve) => {
    const timer = window.setTimeout(resolve, ms)
    signal.addEventListener('abort', () => {
      window.clearTimeout(timer)
      resolve()
    })
  })

export function useEventStream(): StreamStatus {
  const queryClient = useQueryClient()
  const toast = useToast()
  const { session } = useAuth()
  const [status, setStatus] = useState<StreamStatus>('off')

  useEffect(() => {
    if (!session?.tenantId) return
    const controller = new AbortController()
    let after = new Date().toISOString()
    let attempt = 0

    const handle = (event: Payload) => {
      for (const [prefix, targets] of INVALIDATE) {
        if (!event.name.startsWith(prefix)) continue
        for (const queryKey of targets) void queryClient.invalidateQueries({ queryKey })
      }
      const tone = NOTIFY[event.name]
      if (tone) toast.push({ tone, title: eventName(event.name) })
    }

    const run = async () => {
      while (!controller.signal.aborted) {
        try {
          setStatus(attempt ? 'retrying' : 'connecting')
          const response = await fetch(buildUrl('/v1/stream', { after, timeout: 300 }), {
            headers: { ...authHeaders(), Accept: 'text/event-stream' },
            signal: controller.signal,
          })
          // Token vencido: quem desloga é a próxima chamada da API.
          if (response.status === 401) {
            setStatus('off')
            return
          }
          if (!response.ok || !response.body) throw new Error(`stream: ${response.status}`)

          setStatus('live')
          attempt = 0
          const reader = response.body.pipeThrough(new TextDecoderStream()).getReader()
          let buffer = ''
          for (;;) {
            const { value, done } = await reader.read()
            if (done) break
            buffer += value.replaceAll('\r\n', '\n')
            let cut = buffer.indexOf('\n\n')
            while (cut >= 0) {
              const event = parse(buffer.slice(0, cut))
              buffer = buffer.slice(cut + 2)
              cut = buffer.indexOf('\n\n')
              if (!event) continue
              const data = JSON.parse(event.data) as Partial<Payload> & { after?: string }
              if (event.name === 'stream.end') {
                if (data.after) after = data.after
                continue
              }
              if (data.created_at) after = data.created_at
              handle(data as Payload)
            }
          }
        } catch {
          if (controller.signal.aborted) return
          attempt += 1
          setStatus('retrying')
          await sleep(Math.min(30_000, 1000 * 2 ** attempt), controller.signal)
        }
      }
    }

    void run()
    return () => {
      controller.abort()
      setStatus('off')
    }
  }, [session?.tenantId, session?.token, queryClient, toast])

  return status
}
