import { AlertTriangle, FolderUp, Upload } from 'lucide-react'
import { useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { useCompleteUpload, useCreateCollection } from '@/api/queries'
import { useToolFarms, useToolFields } from '@/platform/api'
import type { CollectionKind, CollectionSource } from '@/api/types'
import { Badge, Button, Card, CardHeader, ErrorBox, FormField, Meter, PageHeader } from '@/components/ui'
import { bytes } from '@/lib/labels'
import { uploadCollection, type UploadHandle, type UploadProgress } from '@/lib/upload'

/**
 * Importar Coleta.
 *
 * O formulário do MVP: o voo é de um operador terceirizado, os arquivos chegam
 * pela mão de alguém, e alguém da ValTexa os registra aqui.
 *
 * Duas decisões de tela valem explicar:
 *
 * **O aviso de "sem modelo" aparece antes do upload.** A coleta é criada logo que
 * o talhão e o tipo estão escolhidos, e o servidor já responde qual modelo vai
 * atendê-la. Quem estiver subindo 1.500 fotos aéreas de café descobre no
 * formulário que nenhum modelo treinado as analisa — não meia hora depois.
 *
 * **O progresso é por bytes, não por arquivo.** Num voo, um ortomosaico de 3 GB
 * convive com centenas de quadros de 8 MB; contar arquivos faria a barra ficar
 * parada em 99% por meia hora.
 */
export default function ImportCollection() {
  const navigate = useNavigate()
  const farms = useToolFarms()
  const fields = useToolFields()
  const criar = useCreateCollection()
  const concluir = useCompleteUpload()

  const [farmId, setFarmId] = useState('')
  const [fieldId, setFieldId] = useState('')
  const [collectedOn, setCollectedOn] = useState(() => new Date().toISOString().slice(0, 10))
  const [source, setSource] = useState<CollectionSource>('drone_third_party')
  const [kind, setKind] = useState<CollectionKind>('aerial_image')
  const [operator, setOperator] = useState('')
  const [notes, setNotes] = useState('')
  const [arquivos, setArquivos] = useState<File[]>([])
  const [progresso, setProgresso] = useState<UploadProgress | null>(null)
  const [erro, setErro] = useState<unknown>(null)
  const envio = useRef<UploadHandle | null>(null)
  const entrada = useRef<HTMLInputElement>(null)

  const talhoes = useMemo(
    () => (fields.data ?? []).filter((item) => !farmId || item.farm_id === farmId),
    [fields.data, farmId],
  )
  const totalBytes = arquivos.reduce((soma, item) => soma + item.size, 0)
  const enviando = progresso !== null && progresso.percent < 100 && !progresso.files.every((f) => f.state !== 'uploading')
  const pronto = Boolean(fieldId && collectedOn && arquivos.length)

  async function iniciar() {
    setErro(null)
    try {
      const coleta = await criar.mutateAsync({
        field_id: fieldId,
        collected_on: collectedOn,
        source,
        kind,
        operator_name: operator || null,
        notes: notes || null,
      })

      const controle = uploadCollection(coleta.id, arquivos, setProgresso)
      envio.current = controle
      const final = await controle.promise

      // O upload termina; o processamento começa no worker. Quem fecha a aba
      // agora não perde nada — a coleta continua andando sozinha.
      if (final.filesDone > 0) await concluir.mutateAsync(coleta.id)
      navigate(`/plataforma/coletas/${coleta.id}`)
    } catch (falha) {
      setErro(falha)
    }
  }

  return (
    <>
      <PageHeader
        title="Importar coleta"
        subtitle="O voo é do operador terceirizado. Aqui a ValTexa registra de onde vieram as imagens, a que talhão pertencem e manda para a fila."
      />

      <ErrorBox error={erro ?? criar.error} className="mb-4" />

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader title="De quem e de onde" />
          <div className="grid gap-4 p-4 sm:grid-cols-2">
            <FormField label="Propriedade">
              <select
                className="input"
                value={farmId}
                onChange={(evento) => {
                  setFarmId(evento.target.value)
                  setFieldId('')
                }}
              >
                <option value="">Selecione…</option>
                {(farms.data ?? []).map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </select>
            </FormField>

            <FormField label="Talhão">
              <select
                className="input"
                value={fieldId}
                onChange={(evento) => setFieldId(evento.target.value)}
                disabled={!talhoes.length}
              >
                <option value="">Selecione…</option>
                {talhoes.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </select>
            </FormField>

            <FormField label="Data da coleta" hint="A do voo, não a do upload.">
              <input
                className="input"
                type="date"
                value={collectedOn}
                onChange={(evento) => setCollectedOn(evento.target.value)}
              />
            </FormField>

            <FormField label="Origem">
              <select
                className="input"
                value={source}
                onChange={(evento) => setSource(evento.target.value as CollectionSource)}
              >
                <option value="drone_third_party">Drone terceirizado</option>
                <option value="handheld">Câmera de mão</option>
                <option value="rover">Rover ValTexa</option>
              </select>
            </FormField>

            <FormField label="Tipo" hint="Decide qual modelo pode analisar as imagens.">
              <select
                className="input"
                value={kind}
                onChange={(evento) => setKind(evento.target.value as CollectionKind)}
              >
                <option value="aerial_image">Imagem aérea</option>
                <option value="orthomosaic">Ortomosaico</option>
                <option value="ground_image">Imagem de solo</option>
                <option value="other">Outro</option>
              </select>
            </FormField>

            <FormField label="Operador" hint="Empresa ou piloto que fez o voo.">
              <input
                className="input"
                value={operator}
                onChange={(evento) => setOperator(evento.target.value)}
                placeholder="Drones do Sul"
              />
            </FormField>

            <div className="sm:col-span-2">
              <FormField label="Observações">
                <textarea
                  className="input min-h-20"
                  value={notes}
                  onChange={(evento) => setNotes(evento.target.value)}
                  placeholder="Condição do voo, altura, sobreposição, o que o operador informou."
                />
              </FormField>
            </div>
          </div>
        </Card>

        <Card>
          <CardHeader
            title="Arquivos"
            actions={
              arquivos.length ? (
                <Badge tone="info">
                  {arquivos.length} arquivo{arquivos.length > 1 ? 's' : ''} · {bytes(totalBytes)}
                </Badge>
              ) : null
            }
          />
          <div className="p-4">
            <button
              type="button"
              onClick={() => entrada.current?.click()}
              disabled={enviando}
              className="flex w-full flex-col items-center gap-2 rounded-lg border border-dashed border-line px-6 py-10 text-center text-sm text-muted transition hover:border-accent hover:text-fg disabled:opacity-50"
            >
              <FolderUp className="size-6" aria-hidden />
              <span className="font-medium text-fg">Selecionar arquivos ou uma pasta inteira</span>
              <span>
                Sem limite de quantidade ou tamanho aqui: o teto é o do armazenamento contratado. Cada
                arquivo sobe em pedaços e retoma de onde parou se a conexão cair.
              </span>
            </button>
            <input
              ref={entrada}
              type="file"
              multiple
              accept="image/jpeg,image/png,image/webp,image/tiff,.jpg,.jpeg,.png,.webp,.tif,.tiff"
              className="hidden"
              onChange={(evento) => setArquivos(Array.from(evento.target.files ?? []))}
            />

            {progresso && (
              <div className="mt-4 space-y-2">
                <Meter
                  value={progresso.percent}
                  label={`${bytes(progresso.bytesSent)} de ${bytes(progresso.bytesTotal)} · ${progresso.filesDone}/${progresso.files.length} arquivos`}
                />
                {progresso.files.some((item) => item.state === 'error') && (
                  <p className="flex items-start gap-2 text-[13px] text-critical">
                    <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden />
                    {progresso.files.filter((item) => item.state === 'error').length} arquivo(s) não
                    subiram. A coleta segue com o resto; os que faltarem aparecem marcados no detalhe.
                  </p>
                )}
              </div>
            )}

            <div className="mt-4 flex gap-2">
              <Button onClick={iniciar} disabled={!pronto || enviando || criar.isPending}>
                <Upload className="size-4" aria-hidden />
                {enviando ? 'Enviando…' : 'Iniciar processamento'}
              </Button>
              {enviando && (
                <Button
                  variant="ghost"
                  onClick={() => {
                    envio.current?.cancel()
                    setProgresso(null)
                  }}
                >
                  Parar
                </Button>
              )}
            </div>
            <p className="mt-3 text-[12px] text-muted">
              Depois de iniciar, pode fechar esta aba. O processamento roda no servidor e o progresso
              fica no detalhe da coleta.
            </p>
          </div>
        </Card>
      </div>
    </>
  )
}
