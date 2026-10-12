import { PackageCheck, Send, Upload } from 'lucide-react'
import { useMemo, useState } from 'react'

import { Badge, Button, Card, CardHeader, Empty, ErrorBox, FormField, Modal, PageHeader, Spinner, Table, td, th, useToast } from '@/components/ui'
import { fmt } from '@/lib/format'
import { OTA_FINAIS, otaKindLabel, otaResumo, otaStateLabel, otaStateTone, podeCancelar } from '@/lib/ota'
import {
  OTA_KINDS,
  otaDeploymentBody,
  otaPublishErrors,
  otaPublishQuery,
  otaTargetErrors,
  publishableVersions,
  robotArtifact,
  type OtaKind,
  type OtaTarget,
} from '@/lib/platformForms'
import {
  useCancelOta,
  useDeployOta,
  useModelRegistry,
  useOtaDeployments,
  useOtaPackages,
  usePlatformFleet,
  usePlatformMe,
  usePlatformTenants,
  usePublishOta,
  type OtaPackage,
} from '@/platform/api'

/**
 * Atualizações remotas (OTA, brief seção 24): publicar o pacote, destinar a robôs ou a
 * um cliente inteiro e acompanhar cada robô.
 *
 * O pacote é um `.tar`; o de modelo só entra com a versão em PRODUÇÃO no registry e
 * com o artefato daquela versão dentro (o servidor confere o hash — ver docs/OTA.md).
 * Destinar cria um envelope assinado por robô; cancelar vale até a instalação.
 */
export default function PlatformOta() {
  const [estado, setEstado] = useState('')
  const [publicar, setPublicar] = useState(false)
  const [destinar, setDestinar] = useState<OtaPackage | null>(null)
  const me = usePlatformMe()
  const pode = (me.data?.capabilities ?? []).includes('platform:ota:manage')
  const pacotes = useOtaPackages()
  const destinos = useOtaDeployments({ state: estado || undefined })
  const cancelar = useCancelOta()
  const toast = useToast()
  const linhas = destinos.data ?? []
  const resumo = otaResumo(linhas.map((d) => d.state))

  return (
    <>
      <PageHeader
        eyebrow="Console da plataforma"
        title="Atualizações (OTA)"
        subtitle="Pacotes assinados de Runtime, Edge AI, modelo e configuração. O robô confere assinatura e hash, instala ao lado, testa e só então troca; se o novo não sobe, volta sozinho."
      />
      <div className="mb-4 flex flex-wrap items-center gap-3 text-[13px]">
        <select className="input w-56" value={estado} onChange={(e) => setEstado(e.target.value)} aria-label="Estado">
          <option value="">Todos os estados</option>
          {['pendente', 'baixando', 'verificando_saude', 'aplicada', 'revertida', 'falhou', 'recusada', 'cancelada'].map((s) => (
            <option key={s} value={s}>
              {otaStateLabel(s)}
            </option>
          ))}
        </select>
        <Badge tone="good">{resumo.aplicadas} aplicada(s)</Badge>
        <Badge tone="info">{resumo.emCurso} em curso</Badge>
        <Badge tone={resumo.problemas ? 'critical' : 'neutral'}>{resumo.problemas} com problema</Badge>
        <span className="text-muted">{pacotes.data?.length ?? 0} pacote(s) publicados</span>
        {pode && (
          <Button variant="primary" icon={<Upload className="size-4" />} onClick={() => setPublicar(true)}>
            Publicar pacote
          </Button>
        )}
      </div>

      <Card className="mb-4 overflow-hidden p-0">
        <CardHeader title="Pacotes publicados" subtitle="Pacote não se reescreve: versão nova é pacote novo." />
        <ErrorBox error={pacotes.error} className="mx-5 mb-3" />
        {pacotes.data && pacotes.data.length === 0 && <Empty title="Nenhum pacote publicado" />}
        {!!pacotes.data?.length && (
          <Table>
            <thead>
              <tr>
                <th className={th}>Pacote</th>
                <th className={th}>Conteúdo</th>
                <th className={th}>Tamanho</th>
                <th className={th}>Publicado</th>
                <th className={th} />
              </tr>
            </thead>
            <tbody>
              {pacotes.data.map((p) => (
                <tr key={p.id}>
                  <td className={td}>
                    <div className="font-medium">{otaKindLabel(p.kind)}</div>
                    <div className="num text-[12px] text-muted">{p.version}</div>
                  </td>
                  <td className={`${td} text-[12px]`}>
                    {resumoManifesto(p)}
                    {p.notes && <div className="text-muted">{p.notes}</div>}
                  </td>
                  <td className={`${td} num text-[12px]`}>{fmt.number(p.size_bytes / 1024, 1)} KB</td>
                  <td className={`${td} text-[12px]`}>{fmt.ago(p.created_at)}</td>
                  <td className={td}>
                    {pode && (
                      <Button size="sm" icon={<Send className="size-4" />} onClick={() => setDestinar(p)}>
                        Destinar
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>
      {publicar && <PublicarModal onClose={() => setPublicar(false)} onPublicado={(p) => { setPublicar(false); setDestinar(p) }} />}
      {destinar && <DestinarModal pacote={destinar} onClose={() => setDestinar(null)} />}

      <Card className="overflow-hidden p-0">
        <CardHeader title="Acompanhamento por robô" subtitle="Estado informado pelo próprio robô; atualiza a cada 15 s." />
        {destinos.isLoading && <Spinner />}
        <ErrorBox error={destinos.error} className="m-4" />
        {destinos.data && linhas.length === 0 && (
          <Empty title="Nenhuma atualização com esse filtro" icon={<PackageCheck className="size-5" />}>
            Publique um pacote e destine-o a robôs ou a um cliente.
          </Empty>
        )}
        {linhas.length > 0 && (
          <Table>
            <thead>
              <tr>
                <th className={th}>Pacote</th>
                <th className={th}>Robô</th>
                <th className={th}>Estado</th>
                <th className={th}>Baixado</th>
                <th className={th}>Desde</th>
                <th className={th} />
              </tr>
            </thead>
            <tbody>
              {linhas.map((d) => (
                <tr key={d.id}>
                  <td className={td}>
                    <div className="font-medium">{otaKindLabel(d.kind)}</div>
                    <div className="num text-[12px] text-muted">{d.version}</div>
                  </td>
                  <td className={td}>
                    <div className="num">{d.device_serial}</div>
                    <div className="text-[12px] text-muted">{d.tenant_name}</div>
                  </td>
                  <td className={td}>
                    <Badge tone={otaStateTone(d.state)}>{otaStateLabel(d.state)}</Badge>
                    {d.detail && <div className="mt-1 max-w-72 text-[12px] text-ink-2">{d.detail}</div>}
                  </td>
                  <td className={`${td} num text-[12px]`}>
                    {fmt.percent(d.size_bytes ? Math.min(1, d.bytes_served / d.size_bytes) : 0)}
                  </td>
                  <td className={`${td} text-[12px]`}>{fmt.ago(d.finished_at ?? d.created_at)}</td>
                  <td className={td}>
                    {pode && podeCancelar(d.state) && !OTA_FINAIS.has(d.state) && (
                      <Button
                        variant="ghost"
                        onClick={() =>
                          cancelar.mutate(d.id, {
                            onSuccess: () => toast.push({ tone: 'good', title: 'Atualização cancelada' }),
                          })
                        }
                      >
                        Cancelar
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>
    </>
  )
}

function resumoManifesto(p: OtaPackage): string {
  const m = p.manifest as { files?: { path: string }[]; model?: { model_key: string; version: string; artifact_kind: string } | null }
  const arquivos = m.files?.length ?? 0
  if (m.model) return `${m.model.model_key} ${m.model.version} (artefato ${m.model.artifact_kind}) · ${arquivos} arquivo(s)`
  return `${arquivos} arquivo(s)`
}

function PublicarModal({ onClose, onPublicado }: { onClose: () => void; onPublicado: (p: OtaPackage) => void }) {
  const registry = useModelRegistry()
  const publicar = usePublishOta()
  const toast = useToast()
  const [kind, setKind] = useState<OtaKind | ''>('')
  const [version, setVersion] = useState('')
  const [modelVersionId, setModelVersionId] = useState('')
  const [notes, setNotes] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [tentou, setTentou] = useState(false)
  const versoes = useMemo(() => publishableVersions(registry.data ?? []), [registry.data])
  const escolhida = versoes.find((v) => v.id === modelVersionId)
  const artefato = escolhida ? robotArtifact(escolhida) : null
  const form = { kind, version, modelVersionId, notes, file: file ? { name: file.name, size: file.size } : null }
  const erros = otaPublishErrors(form)

  const enviar = () => {
    setTentou(true)
    if (erros.length || !file) return
    publicar.mutate(
      { file, query: otaPublishQuery(form) },
      {
        onSuccess: (p) => {
          toast.push({ tone: 'good', title: `Pacote ${p.version} publicado` })
          onPublicado(p)
        },
      },
    )
  }

  return (
    <Modal
      open
      onClose={onClose}
      title="Publicar pacote OTA"
      description="O .tar vai para o armazenamento com o hash; o robô confere assinatura e hash antes de instalar."
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancelar
          </Button>
          <Button variant="primary" loading={publicar.isPending} onClick={enviar}>
            Publicar
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        <FormField label="Tipo">
          <select className="input" value={kind} onChange={(e) => setKind(e.target.value as OtaKind)} aria-label="Tipo do pacote">
            <option value="">Escolha…</option>
            {OTA_KINDS.map((k) => (
              <option key={k} value={k}>
                {otaKindLabel(k)}
              </option>
            ))}
          </select>
        </FormField>
        {kind === 'model' && (
          <FormField label="Versão do registry (em PRODUÇÃO)">
            <select className="input" value={modelVersionId} onChange={(e) => setModelVersionId(e.target.value)} aria-label="Versão do modelo">
              <option value="">Escolha…</option>
              {versoes.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.model_key} {v.version}
                </option>
              ))}
            </select>
            {!registry.isLoading && !versoes.length && (
              <span className="mt-1 block text-[12px] text-warning">Nenhuma versão em PRODUÇÃO com artefato registrado.</span>
            )}
            {!artefato && versoes.length > 0 && (
              <span className="mt-1 block text-[12px] text-muted">
                {versoes.length} versão(ões) em PRODUÇÃO com artefato; o .tar precisa conter o artefato da escolhida.
              </span>
            )}
            {artefato && (
              <span className="mt-1 block text-[12px] text-muted">
                O .tar precisa conter <code className="num">{artefato.file}</code> (artefato {artefato.kind}).
              </span>
            )}
          </FormField>
        )}
        <FormField label="Versão do pacote">
          <input className="input" value={version} onChange={(e) => setVersion(e.target.value)} placeholder="ex.: cfg-2026-10-05" aria-label="Versão do pacote" />
        </FormField>
        <FormField label="Arquivo .tar">
          <input
            type="file"
            accept=".tar,application/x-tar"
            className="text-[13px]"
            aria-label="Arquivo do pacote"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
          {file && <span className="mt-1 block text-[12px] text-muted">{file.name} · {fmt.number(file.size / 1024, 1)} KB</span>}
        </FormField>
        <FormField label="Notas (opcional)">
          <input className="input" value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={1000} aria-label="Notas" />
        </FormField>
        {tentou && erros.length > 0 && (
          <ul className="text-[12px] text-critical">
            {erros.map((e) => (
              <li key={e}>{e}</li>
            ))}
          </ul>
        )}
        <ErrorBox error={publicar.error} />
      </div>
    </Modal>
  )
}

function DestinarModal({ pacote, onClose }: { pacote: OtaPackage; onClose: () => void }) {
  const clientes = usePlatformTenants()
  const [modo, setModo] = useState<'cliente' | 'robos'>('robos')
  const [tenantId, setTenantId] = useState('')
  const [robos, setRobos] = useState<string[]>([])
  const frota = usePlatformFleet({ tenant_id: tenantId || undefined })
  const destinar = useDeployOta()
  const toast = useToast()
  const alvo: OtaTarget = modo === 'cliente' ? { mode: 'cliente', tenantId } : { mode: 'robos', deviceIds: robos }
  const erros = otaTargetErrors(alvo)
  const rovers = (frota.data ?? []).filter((d) => d.kind === 'rover')

  const enviar = () => {
    if (erros.length) return
    destinar.mutate(otaDeploymentBody(pacote.id, alvo), {
      onSuccess: (lista) => {
        toast.push({ tone: 'good', title: `${lista.length} robô(s) vão receber ${pacote.version}` })
        onClose()
      },
    })
  }

  return (
    <Modal
      open
      onClose={onClose}
      title={`Destinar ${otaKindLabel(pacote.kind)} ${pacote.version}`}
      description="Cada robô recebe um envelope assinado; quem já tem esta versão pendente não recebe outra."
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancelar
          </Button>
          <Button variant="primary" loading={destinar.isPending} disabled={erros.length > 0} onClick={enviar}>
            Destinar
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-3 text-[13px]">
        <FormField label="Cliente">
          <select className="input" value={tenantId} onChange={(e) => { setTenantId(e.target.value); setRobos([]) }} aria-label="Cliente">
            <option value="">Todos os clientes</option>
            {clientes.data?.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
        </FormField>
        <div className="flex gap-4">
          <label className="flex items-center gap-2">
            <input type="radio" checked={modo === 'robos'} onChange={() => setModo('robos')} /> Robôs escolhidos
          </label>
          <label className="flex items-center gap-2">
            <input type="radio" checked={modo === 'cliente'} onChange={() => setModo('cliente')} disabled={!tenantId} /> Todos os robôs do cliente
          </label>
        </div>
        {modo === 'robos' && (
          <div className="max-h-64 overflow-y-auto rounded-md border border-line-soft p-2">
            {frota.isLoading && <Spinner />}
            {!frota.isLoading && !rovers.length && <span className="text-muted">Nenhum robô.</span>}
            {rovers.map((d) => (
              <label key={d.id} className="flex items-center gap-2 py-1">
                <input
                  type="checkbox"
                  checked={robos.includes(d.id)}
                  onChange={(e) => setRobos((r) => (e.target.checked ? [...r, d.id] : r.filter((x) => x !== d.id)))}
                  aria-label={`Robô ${d.serial_number}`}
                />
                <span className="num">{d.serial_number}</span>
                <span className="text-muted">
                  {d.name} · {d.tenant_name}
                </span>
              </label>
            ))}
          </div>
        )}
        {erros.length > 0 && <span className="text-[12px] text-muted">{erros.join(' ')}</span>}
        <ErrorBox error={destinar.error} />
      </div>
    </Modal>
  )
}
