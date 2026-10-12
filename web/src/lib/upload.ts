/**
 * Envio de coleta grande, do navegador.
 *
 * O problema concreto: um voo de talhão são centenas de arquivos e dezenas de
 * gigabytes. Um `<input type="file">` com tudo num `FormData` monta o corpo
 * inteiro na memória da aba, não tem progresso confiável e, se a internet da
 * fazenda oscilar aos 40 minutos, recomeça do zero.
 *
 * O que este módulo faz:
 *
 * - **declara** todos os arquivos antes de mandar byte nenhum, o que dá um total
 *   conhecido desde o início e uma barra de progresso que não mente;
 * - **fatia** cada arquivo com `Blob.slice`, que é uma janela sobre o arquivo em
 *   disco — a memória da aba não cresce com o tamanho do arquivo;
 * - **retoma** de `received_bytes`: quando o servidor devolve 409, o cabeçalho
 *   `X-Received-Bytes` diz de onde continuar, e o pedaço seguinte sai dali;
 * - **paraleliza por arquivo**, não dentro do arquivo. Quatro conexões dão a
 *   banda disponível sem exigir montagem fora de ordem no servidor.
 *
 * Nenhum limite de tamanho é imposto aqui. O teto é o do armazenamento
 * contratado, e quem o aplica é a infraestrutura.
 */
import { authHeaders, buildUrl } from '@/api/client'

/** Tamanho de um pedaço. Abaixo do teto do servidor, com folga. */
export const CHUNK_BYTES = 4 * 1024 * 1024

/** Arquivos enviados ao mesmo tempo. Mais que isso disputa banda sem ganhar. */
export const CONCURRENCY = 4

export type FileProgress = {
  name: string
  size: number
  sent: number
  state: 'pending' | 'uploading' | 'done' | 'error'
  error?: string
}

export type UploadProgress = {
  files: FileProgress[]
  filesDone: number
  bytesSent: number
  bytesTotal: number
  percent: number
}

type DeclaredFile = { id: string; filename: string; size_bytes: number; received_bytes: number }

export type UploadHandle = {
  promise: Promise<UploadProgress>
  cancel: () => void
}

/**
 * Declara os arquivos e envia todos, avisando o progresso a cada pedaço.
 *
 * Devolve um controle com `cancel`: quem fecha o modal no meio para o envio, e
 * o que já subiu continua no servidor — a coleta é retomável por construção.
 */
export function uploadCollection(
  collectionId: string,
  files: File[],
  onProgress: (progress: UploadProgress) => void,
): UploadHandle {
  const controller = new AbortController()
  const promise = run(collectionId, files, onProgress, controller.signal)
  return { promise, cancel: () => controller.abort() }
}

async function run(
  collectionId: string,
  files: File[],
  onProgress: (progress: UploadProgress) => void,
  signal: AbortSignal,
): Promise<UploadProgress> {
  const estado: UploadProgress = {
    files: files.map((file) => ({ name: file.name, size: file.size, sent: 0, state: 'pending' })),
    filesDone: 0,
    bytesSent: 0,
    bytesTotal: files.reduce((soma, file) => soma + file.size, 0),
    percent: 0,
  }
  const aviso = () => {
    estado.percent = estado.bytesTotal ? (estado.bytesSent / estado.bytesTotal) * 100 : 0
    onProgress({ ...estado, files: [...estado.files] })
  }
  aviso()

  const declarados = await declare(collectionId, files, signal)

  // Fila simples: cada worker puxa o próximo índice livre. Mantém as quatro
  // conexões ocupadas mesmo com arquivos de tamanhos muito diferentes — o que é
  // a regra num voo, onde um ortomosaico convive com centenas de quadros.
  let proximo = 0
  const worker = async () => {
    for (;;) {
      const indice = proximo++
      if (indice >= files.length || signal.aborted) return
      const arquivo = files[indice]
      const declarado = declarados[indice]
      const linha = estado.files[indice]
      if (!arquivo || !declarado || !linha) return

      linha.state = 'uploading'
      try {
        await sendFile(collectionId, declarado, arquivo, signal, (delta) => {
          linha.sent += delta
          estado.bytesSent += delta
          aviso()
        })
        linha.state = 'done'
        estado.filesDone += 1
      } catch (erro) {
        if (signal.aborted) return
        linha.state = 'error'
        linha.error = erro instanceof Error ? erro.message : String(erro)
      }
      aviso()
    }
  }

  await Promise.all(Array.from({ length: Math.min(CONCURRENCY, files.length) }, worker))
  return estado
}

async function declare(
  collectionId: string,
  files: File[],
  signal: AbortSignal,
): Promise<DeclaredFile[]> {
  const resposta = await fetch(buildUrl(`/v1/admin/collections/${collectionId}/files`), {
    method: 'POST',
    headers: { ...authHeaders(), 'Content-Type': 'application/json' },
    body: JSON.stringify({
      files: files.map((file) => ({
        filename: file.name,
        size_bytes: file.size,
        content_type: file.type || null,
        captured_at: file.lastModified ? new Date(file.lastModified).toISOString() : null,
      })),
    }),
    signal,
  })
  if (!resposta.ok) throw new Error(await detalhe(resposta))
  return (await resposta.json()) as DeclaredFile[]
}

async function sendFile(
  collectionId: string,
  declarado: DeclaredFile,
  file: File,
  signal: AbortSignal,
  onChunk: (delta: number) => void,
): Promise<void> {
  const rota = `/v1/admin/collections/${collectionId}/files/${declarado.id}/chunk`
  let offset = declarado.received_bytes

  while (offset < file.size) {
    if (signal.aborted) return
    const fim = Math.min(offset + CHUNK_BYTES, file.size)
    const resposta = await fetch(buildUrl(rota, { offset }), {
      method: 'PUT',
      headers: { ...authHeaders(), 'Content-Type': 'application/octet-stream' },
      body: file.slice(offset, fim),
      signal,
    })

    if (resposta.status === 409) {
      // O servidor está noutro ponto: ou um envio anterior chegou e a resposta
      // se perdeu, ou esta aba está atrasada. Ele diz onde está; seguimos dali.
      const recebido = Number(resposta.headers.get('X-Received-Bytes') ?? offset)
      onChunk(Math.max(0, recebido - offset))
      offset = recebido
      continue
    }
    if (!resposta.ok) throw new Error(await detalhe(resposta))

    const corpo = (await resposta.json()) as { received_bytes: number }
    onChunk(Math.max(0, corpo.received_bytes - offset))
    offset = corpo.received_bytes
  }
}

async function detalhe(resposta: Response): Promise<string> {
  try {
    const corpo = (await resposta.json()) as { detail?: string }
    return corpo.detail ?? `Erro ${resposta.status}`
  } catch {
    return resposta.statusText || `Erro ${resposta.status}`
  }
}
