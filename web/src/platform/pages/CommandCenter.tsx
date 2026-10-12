import {
  Activity,
  Bot,
  BrainCircuit,
  Camera,
  Compass,
  Gamepad2,
  ListChecks,
  OctagonX,
  Pause,
  Pin,
  PinOff,
  Play,
  Power,
  RadioTower,
  RefreshCw,
  RotateCcw,
  ScanLine,
  Settings2,
  Square,
} from 'lucide-react'
import { useCallback, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { TimeSeries } from '@/components/charts'
import { Badge, Button, Card, CardHeader, Empty, ErrorBox, PageHeader, Spinner, Table, td, th, useToast } from '@/components/ui'
import {
  CONFIG_PRESETS,
  type Mode,
  MODES,
  commandLabel,
  commandState,
  commandSummary,
  latestPhotos,
  modeInfo,
  partLabel,
  partsFromReport,
} from '@/lib/comando'
import { resumoDoEnlace, rotuloDoEnlace, tomDoEnlace, trechos } from '@/lib/enlace'
import { fleetStateLabel, fleetStateTone, faultText } from '@/lib/fleet'
import { fmt } from '@/lib/format'
import {
  type RoverPanel,
  useCancelRoverCommand,
  usePinRoverModel,
  usePlatformFleet,
  usePlatformMe,
  useRoverCommand,
  useRoverModels,
  useRoverPanel,
} from '@/platform/api'
import { EstacaoDePilotagem } from '@/platform/pages/Pilotagem'

/**
 * Centro de comando do Rover (console da plataforma).
 *
 * Tudo o que se manda ao robô sai assinado pelo servidor e é conferido pelo robô antes
 * de obedecer; esta tela só pede. O estado mostrado é o que o robô respondeu — nunca o
 * que a tela supõe. Atualiza a cada 2 s.
 */

const PODE = 'platform:rover:control'

export function CommandCenterList() {
  const frota = usePlatformFleet({})
  const rovers = (frota.data ?? []).filter((d) => String(d.kind ?? '').toLowerCase().includes('rover') || d.model_code?.startsWith('ROVER'))
  return (
    <>
      <PageHeader
        eyebrow="Console da plataforma"
        title="Centro de comando"
        subtitle="Escolha um rover para ver cada peça, testar, mudar o modo, dirigir no controle remoto, trocar a configuração e fixar o modelo de IA."
        actions={
          <Link to="/plataforma/comando/bases">
            <Button variant="secondary">
              <RadioTower className="size-4" /> Bases da fazenda
            </Button>
          </Link>
        }
      />
      <Card className="overflow-hidden p-0">
        {frota.isLoading && <Spinner />}
        <ErrorBox error={frota.error} className="m-4" />
        {frota.data && rovers.length === 0 && (
          <Empty title="Nenhum rover na frota" icon={<Bot className="size-5" />}>
            Provisione um rover para ele aparecer aqui.
          </Empty>
        )}
        {rovers.length > 0 && (
          <Table>
            <thead>
              <tr>
                <th className={th}>Rover</th>
                <th className={th}>Cliente</th>
                <th className={th}>Estado</th>
                <th className={th}>Bateria</th>
                <th className={th}>Contato</th>
                <th className={th} />
              </tr>
            </thead>
            <tbody>
              {rovers.map((d) => (
                <tr key={d.id}>
                  <td className={td}>
                    <div className="font-medium">{d.name}</div>
                    <div className="num text-[12px] text-muted">
                      {d.model_code} · {d.serial_number}
                    </div>
                  </td>
                  <td className={td}>{d.tenant_name}</td>
                  <td className={td}>
                    <Badge tone={fleetStateTone(d.fleet_state)}>{d.fleet_state_label}</Badge>
                  </td>
                  <td className={`${td} num`}>{d.battery_percent != null ? `${fmt.number(d.battery_percent)}%` : '—'}</td>
                  <td className={`${td} text-[12px]`}>visto {fmt.ago(d.last_seen_at)}</td>
                  <td className={td}>
                    <Link className="btn-link font-medium text-accent" to={`/plataforma/comando/${d.id}`}>
                      Abrir comando →
                    </Link>
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

export default function CommandCenter() {
  const { id = '' } = useParams()
  const painel = useRoverPanel(id)
  const eu = usePlatformMe()
  const pode = Boolean(eu.data?.capabilities?.includes(PODE))
  const comando = useRoverCommand(id)
  const toast = useToast()

  const manda = useCallback(
    (kind: string, params: Record<string, unknown> = {}, ok?: string) =>
      comando.mutate(
        { kind, params },
        {
          onSuccess: () => toast.push({ tone: 'info', title: ok ?? `${commandLabel(kind)} enviado`, detail: 'Assinado; o rover executa na próxima busca (≤ 2 s).' }),
          onError: (e) => toast.push({ tone: 'critical', title: `${commandLabel(kind)} recusado`, detail: String((e as Error).message) }),
        },
      ),
    [comando, toast],
  )

  if (painel.isLoading) return <Spinner label="Conectando ao rover" />
  if (painel.error || !painel.data) return <ErrorBox error={painel.error} />
  const p = painel.data
  const d = p.device
  const modo = modeInfo(p.control_mode)

  return (
    <>
      {/* Barra de missão: o que importa num olhar, e o botão de parada sempre à mão */}
      <div className="mb-5 overflow-hidden rounded-2xl border border-line bg-[#07130e] text-[#d6efe2] shadow-lg">
        <div className="flex flex-wrap items-center gap-x-6 gap-y-3 px-5 py-4">
          <div className="min-w-0">
            <div className="text-[11px] tracking-[0.18em] text-[#7fb59a] uppercase">Centro de comando</div>
            <div className="font-display truncate text-[22px] font-semibold text-white">{d.name}</div>
            <div className="num text-[12px] text-[#9cc9b2]">
              {d.model_code} · {d.serial_number} · {String(d.tenant_name ?? '')}
            </div>
          </div>
          <Telemetria label="Estado" valor={fleetStateLabel(d.fleet_state)} tom={fleetStateTone(d.fleet_state)} />
          <Telemetria label="Modo" valor={modo.label} tom={modo.tone} />
          <Telemetria label="Bateria" valor={d.battery_percent != null ? `${fmt.number(d.battery_percent)}%` : '—'} />
          <Telemetria label="Contato" valor={fmt.ago(d.last_seen_at)} />
          <Telemetria label="Missão" valor={p.mission ? `${p.mission.state} · ${fmt.shortId(p.mission.id)}` : 'nenhuma'} />
          <Link to={`/plataforma/comando/${id}/validacao`} className="ml-auto flex items-center gap-1.5 rounded-lg border border-[#1d3a2c] px-3 py-2 text-[13px] text-[#d6efe2] hover:bg-[#10241a]">
            <ListChecks className="size-4" /> Validação
          </Link>
          <div>
            <button
              type="button"
              disabled={!pode}
              onClick={() => manda('parar', { motivo: 'botão de parada do centro de comando' }, 'PARADA enviada')}
              className="flex items-center gap-2 rounded-xl bg-[#d03b3b] px-5 py-3 text-[15px] font-bold tracking-wide text-white shadow-[0_0_0_3px_rgba(208,59,59,0.35)] hover:brightness-110 disabled:opacity-40"
            >
              <OctagonX className="size-5" /> PARAR
            </button>
          </div>
        </div>
        {(d.active_faults?.length ?? 0) > 0 && (
          <div className="border-t border-[#1d3a2c] bg-[#2a1310] px-5 py-2 text-[12px] text-[#ffb4a6]">
            Falhas ativas: {(d.active_faults ?? []).map(faultText).join(' · ')}
          </div>
        )}
        {!pode && (
          <div className="border-t border-[#1d3a2c] px-5 py-2 text-[12px] text-[#9cc9b2]">
            Somente leitura: comandar um rover exige a permissão "{PODE}" (Operações ou superadmin).
          </div>
        )}
      </div>

      <div className="grid gap-5 xl:grid-cols-3">
        <div className="space-y-5 xl:col-span-2">
          <Modo painel={p} pode={pode} manda={manda} />
          <EstacaoDePilotagem painel={p} id={id} pode={pode} manda={manda} />
          <Pecas painel={p} pode={pode} manda={manda} />
          <Cameras painel={p} pode={pode} manda={manda} />
        </div>
        <div className="space-y-5">
          <CaminhoCard painel={p} />
          <IaEmbarcada painel={p} id={id} pode={pode} manda={manda} />
          <Configuracao pode={pode} manda={manda} />
          <TelemetriaCard painel={p} />
        </div>
      </div>
      <div className="mt-5">
        <Registro painel={p} id={id} pode={pode} />
      </div>
    </>
  )
}

type Manda = (kind: string, params?: Record<string, unknown>, ok?: string) => void

function Telemetria({ label, valor, tom }: { label: string; valor: string; tom?: string }) {
  return (
    <div>
      <div className="text-[11px] tracking-[0.14em] text-[#7fb59a] uppercase">{label}</div>
      <div className="num flex items-center gap-1.5 text-[15px] text-white">
        {tom && <span className={`size-2 rounded-full ${DOT[tom] ?? 'bg-[#7fb59a]'}`} />}
        {valor}
      </div>
    </div>
  )
}

const DOT: Record<string, string> = {
  good: 'bg-good',
  warning: 'bg-warning',
  serious: 'bg-serious',
  critical: 'bg-critical',
  info: 'bg-info',
  accent: 'bg-accent',
  neutral: 'bg-[#7fb59a]',
}

// --- modo de operação -------------------------------------------------------------

const MODE_ICON: Record<Mode, typeof Play> = { autonomo: Play, manual: Gamepad2, pausado: Pause, parado: Square }

function Modo({ painel, pode, manda }: { painel: RoverPanel; pode: boolean; manda: Manda }) {
  const atual = painel.control_mode
  const pendente = painel.commands.find((c) => c.kind === 'modo' && (c.state === 'pendente' || c.state === 'entregue'))
  return (
    <Card>
      <CardHeader
        title={
          <span className="flex items-center gap-2">
            <Compass className="size-4" /> Modo de operação
          </span>
        }
        subtitle="O rover só muda de modo quando confirma. Autônomo segue a rota da missão; manual só anda pelo controle remoto."
      />
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {MODES.map((m) => {
          const info = modeInfo(m)
          const Icon = MODE_ICON[m]
          const ativo = atual === m
          return (
            <button
              key={m}
              type="button"
              disabled={!pode || ativo}
              onClick={() => manda('modo', { modo: m }, `Modo ${info.label} pedido`)}
              className={`rounded-xl border p-3 text-left transition ${ativo ? 'border-accent bg-accent-soft' : 'border-line bg-surface hover:bg-raised'} disabled:cursor-default`}
            >
              <div className="flex items-center gap-2 font-medium">
                <Icon className="size-4" /> {info.label}
                {ativo && <Badge tone={info.tone}>atual</Badge>}
              </div>
              <div className="mt-1 text-[12px] text-ink-2">{info.hint}</div>
            </button>
          )
        })}
      </div>
      {pendente && (
        <div className="mt-3 text-[12px] text-info">
          Pedido de modo "{String(pendente.params.modo)}": {commandState(pendente.state).label.toLowerCase()}…
        </div>
      )}
      <div className="mt-3 text-[12px] text-muted">
        Missão: {painel.mission ? `${painel.mission.kind} ${painel.mission.state} (${fmt.shortId(painel.mission.id)})` : 'nenhuma em execução — despache uma em Missões.'}
      </div>
    </Card>
  )
}

// --- peças ----------------------------------------------------------------------------

function Pecas({ painel, pode, manda }: { painel: RoverPanel; pode: boolean; manda: Manda }) {
  const ultimo = painel.commands.find((c) => c.kind === 'diagnostico' && c.state === 'concluido')
  const linhas = partsFromReport(ultimo?.result)
  const emCurso = painel.commands.find((c) => c.kind === 'diagnostico' && (c.state === 'pendente' || c.state === 'entregue'))
  const saude = painel.health as { cameras?: { id: string; ok: boolean; detail: string | null }[]; sensors?: Record<string, string> } | null
  const fixas = ['gnss', 'imu', 'acelerador', 'sistema', 'disco', 'navegacao', 'lente']
  const cameras = Array.from(new Set([...(saude?.cameras ?? []).map((c) => c.id), ...linhas.filter((l) => l.nome.startsWith('camera:')).map((l) => l.nome.slice(7))]))
  const nomes = [...cameras.map((c) => `camera:${c}`), ...fixas]
  const porNome = new Map(linhas.map((l) => [l.nome, l]))

  return (
    <Card>
      <CardHeader
        title={
          <span className="flex items-center gap-2">
            <ListChecks className="size-4" /> Peças e testes
          </span>
        }
        subtitle={ultimo ? `Último laudo ${fmt.ago(ultimo.finished_at)}${emCurso ? ' — novo teste em curso' : ''}.` : 'Nenhum teste ainda. O laudo lê cada peça uma vez.'}
        actions={
          <Button variant="primary" disabled={!pode || Boolean(emCurso)} onClick={() => manda('diagnostico', { fotos: true }, 'Teste de todas as peças enviado')}>
            <ScanLine className="size-4" /> Testar tudo
          </Button>
        }
      />
      <Table>
        <thead>
          <tr>
            <th className={th}>Peça</th>
            <th className={th}>Último teste</th>
            <th className={th}>Detalhe</th>
            <th className={th} />
          </tr>
        </thead>
        <tbody>
          {nomes.map((nome) => {
            const l = porNome.get(nome)
            return (
              <tr key={nome}>
                <td className={`${td} font-medium`}>{partLabel(nome)}</td>
                <td className={td}>
                  {l ? <Badge tone={l.ok ? 'good' : 'critical'}>{l.ok ? 'OK' : 'Falhou'}</Badge> : <Badge tone="neutral">sem teste</Badge>}
                </td>
                <td className={`${td} num max-w-md text-[12px] text-ink-2`}>{l ? (l.erro ?? resumoDetalhe(l.detalhe)) : '—'}</td>
                <td className={td}>
                  <Button
                    variant="ghost"
                    disabled={!pode}
                    onClick={() =>
                      manda('diagnostico', { pecas: [nome], fotos: nome.startsWith('camera:') }, `Teste de ${partLabel(nome)} enviado`)
                    }
                  >
                    Testar
                  </Button>
                </td>
              </tr>
            )
          })}
        </tbody>
      </Table>
    </Card>
  )
}

function resumoDetalhe(d: Record<string, unknown>): string {
  return Object.entries(d)
    .filter(([, v]) => v !== null && v !== undefined && typeof v !== 'object')
    .slice(0, 6)
    .map(([k, v]) => `${k}: ${typeof v === 'number' ? fmt.number(v, 2) : String(v)}`)
    .join(' · ')
}

// --- câmeras --------------------------------------------------------------------------

function Cameras({ painel, pode, manda }: { painel: RoverPanel; pode: boolean; manda: Manda }) {
  const fotos = latestPhotos(painel.commands)
  const saude = painel.health as { cameras?: { id: string; ok: boolean }[] } | null
  const ids = Array.from(new Set([...(saude?.cameras ?? []).map((c) => c.id), ...Object.keys(fotos)])).sort()
  return (
    <Card>
      <CardHeader
        title={
          <span className="flex items-center gap-2">
            <Camera className="size-4" /> Câmeras
          </span>
        }
        subtitle="Foto sob demanda, reduzida; a original fica no rover. Com a distância medida pela profundidade e o campo de visão efetivo (lente corrigida)."
      />
      {ids.length === 0 && <div className="text-[13px] text-muted">O rover ainda não informou as câmeras. Rode "Testar tudo".</div>}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {ids.map((cam) => {
          const f = fotos[cam]
          return (
            <div key={cam} className="overflow-hidden rounded-xl border border-line">
              <div className="aspect-[4/3] bg-[#07130e]">
                {f ? <img src={f.src} alt={`Última foto da câmera ${cam}`} className="size-full object-cover" /> : <div className="grid size-full place-items-center text-[12px] text-[#7fb59a]">sem foto</div>}
              </div>
              <div className="flex items-center justify-between gap-2 px-3 py-2 text-[12px]">
                <div>
                  <div className="font-medium">{cam}</div>
                  <div className="num text-muted">
                    {f
                      ? `${f.detalhe.distancia_mm != null ? `${fmt.number(Number(f.detalhe.distancia_mm), 0)} mm` : 'sem profundidade'} · ${fmt.ago(f.at)}`
                      : '—'}
                  </div>
                </div>
                <Button variant="ghost" disabled={!pode} onClick={() => manda('foto', { camera_id: cam }, `Foto de ${cam} pedida`)}>
                  <Camera className="size-4" />
                </Button>
              </div>
            </div>
          )
        })}
      </div>
    </Card>
  )
}

// --- IA embarcada ---------------------------------------------------------------------

function IaEmbarcada({ painel, id, pode, manda }: { painel: RoverPanel; id: string; pode: boolean; manda: Manda }) {
  const modelos = useRoverModels(id)
  const fixar = usePinRoverModel(id)
  const toast = useToast()
  const [escolha, setEscolha] = useState('')
  const d = painel.device
  const opcoes = modelos.data ?? []

  return (
    <Card>
      <CardHeader
        title={
          <span className="flex items-center gap-2">
            <BrainCircuit className="size-4" /> IA embarcada
          </span>
        }
        subtitle="O que roda agora, o que cada talhão designa, e o modelo fixado pela equipe (vale nos talhões da cultura dele)."
      />
      <div className="space-y-3 text-[13px]">
        <div className="num rounded-lg bg-sunken px-3 py-2">
          rodando: {d.ai_model_key ? `${d.ai_model_key}@${d.ai_model_version}` : 'não informado'}
          <br />
          edge {d.edge_ai_version ?? '—'} · runtime {d.runtime_version ?? '—'}
        </div>
        <div>
          <div className="mb-1 text-muted">Por talhão</div>
          <ul className="space-y-1">
            {painel.designated.map((x) => (
              <li key={x.field_id} className="flex justify-between gap-2">
                <span>
                  {x.field_name} <span className="text-muted">({x.crop})</span>
                </span>
                <span className="num text-right text-[12px]">{x.model ?? x.reason ?? '—'}</span>
              </li>
            ))}
          </ul>
        </div>
        <div className="rounded-lg border border-line p-3">
          <div className="mb-2 flex items-center gap-2 font-medium">
            <Pin className="size-4" /> Modelo fixado: {painel.pinned_model ? `${painel.pinned_model.model_key}@${painel.pinned_model.version}` : 'nenhum (vale o do talhão)'}
          </div>
          <select className="input mb-2 w-full" value={escolha} onChange={(e) => setEscolha(e.target.value)} disabled={!pode} aria-label="Modelo para fixar">
            <option value="">Escolha uma versão do registry…</option>
            {opcoes.map((m) => (
              <option key={`${m.model_key}@${m.version}`} value={`${m.model_key}@${m.version}`}>
                {m.model_key}@{m.version} · {m.state} · {m.crops.join('/')}
                {m.optimized ? ' · otimizado' : ''}
              </option>
            ))}
          </select>
          <div className="flex flex-wrap gap-2">
            <Button
              variant="primary"
              disabled={!pode || !escolha || fixar.isPending}
              onClick={() => {
                const [model_key = null, version = null] = escolha.split('@')
                fixar.mutate(
                  { model_key, version },
                  {
                    onSuccess: () => toast.push({ tone: 'good', title: `Fixado ${escolha}`, detail: 'O rover recarrega os modelos na próxima busca.' }),
                    onError: (e) => toast.push({ tone: 'critical', title: 'Não fixou', detail: String((e as Error).message) }),
                  },
                )
              }}
            >
              <Pin className="size-4" /> Fixar
            </Button>
            <Button
              disabled={!pode || !painel.pinned_model}
              onClick={() => fixar.mutate({ model_key: null, version: null })}
            >
              <PinOff className="size-4" /> Voltar ao do talhão
            </Button>
            <Button variant="ghost" disabled={!pode} onClick={() => manda('recarregar_modelos', {}, 'Recarregar modelos enviado')}>
              <RefreshCw className="size-4" /> Recarregar
            </Button>
          </div>
        </div>
        <div>
          <div className="mb-1 text-muted">Últimos resultados da IA no rover</div>
          <ul className="space-y-1 text-[12px]">
            {painel.recent_results.length === 0 && <li className="text-muted">nenhum</li>}
            {painel.recent_results.map((r) => (
              <li key={r.record_id} className="flex justify-between gap-2">
                <span>
                  <Badge tone={r.type === 'NORMAL' ? 'neutral' : r.type === 'ANOMALIA' ? 'warning' : 'serious'}>{r.type}</Badge> {r.label ?? ''}
                </span>
                <span className="num text-muted">
                  {r.camera_id} · {fmt.ago(r.occurred_at)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </Card>
  )
}

// --- configuração ---------------------------------------------------------------------

function Configuracao({ pode, manda }: { pode: boolean; manda: Manda }) {
  const [texto, setTexto] = useState('{\n  "retencao": {"normal_sample_every": 0}\n}')
  const [erro, setErro] = useState<string | null>(null)
  return (
    <Card>
      <CardHeader
        title={
          <span className="flex items-center gap-2">
            <Settings2 className="size-4" /> Configuração do rover
          </span>
        }
        subtitle="Troca parte do rover.json. O rover valida, troca com backup e reinicia o serviço para valer (como no OTA)."
      />
      <div className="space-y-3 text-[13px]">
        {CONFIG_PRESETS.map((preset) => (
          <div key={preset.id} className="flex items-start justify-between gap-3 rounded-lg border border-line p-3">
            <div>
              <div className="font-medium">{preset.label}</div>
              <div className="text-[12px] text-ink-2">{preset.hint}</div>
            </div>
            <Button disabled={!pode} onClick={() => manda('config', { rover_json: preset.rover_json }, `${preset.label} enviado`)}>
              Aplicar
            </Button>
          </div>
        ))}
        <details>
          <summary className="cursor-pointer text-muted">Avançado: JSON</summary>
          <textarea className="input num mt-2 h-32 w-full font-mono text-[12px]" value={texto} onChange={(e) => setTexto(e.target.value)} aria-label="Trecho do rover.json" />
          {erro && <div className="text-[12px] text-critical">{erro}</div>}
          <Button
            className="mt-2"
            disabled={!pode}
            onClick={() => {
              try {
                const rover_json = JSON.parse(texto)
                setErro(null)
                manda('config', { rover_json }, 'Configuração enviada')
              } catch (e) {
                setErro(`JSON inválido: ${(e as Error).message}`)
              }
            }}
          >
            Enviar configuração
          </Button>
        </details>
        <div className="flex gap-2">
          <Button variant="ghost" disabled={!pode} onClick={() => manda('reiniciar', {}, 'Reinício enviado')}>
            <Power className="size-4" /> Reiniciar serviço
          </Button>
        </div>
      </div>
    </Card>
  )
}

// --- caminho até o rover -------------------------------------------------------------

function CaminhoCard({ painel }: { painel: RoverPanel }) {
  const c = painel.caminho
  return (
    <Card>
      <CardHeader
        title={
          <span className="flex items-center gap-2">
            <RadioTower className="size-4" /> Caminho
          </span>
        }
        subtitle={
          c.modo === 'base'
            ? `Pela base ${c.base.name} (${c.base.serial_number}); retrato ${c.base.reportado_em ? fmt.ago(c.base.reportado_em) : '—'}.`
            : 'O Rover fala direto com a nuvem (nenhuma base da fazenda o cita).'
        }
      />
      <ol className="space-y-2">
        {trechos(c).map((t) => (
          <li key={t.nome} className="flex items-start gap-2 text-[13px]">
            <Badge tone={t.tom}>{t.nome}</Badge>
            <span className="text-muted">{t.detalhe}</span>
          </li>
        ))}
      </ol>
      {c.modo === 'base' && c.base_rover.enlaces.length > 0 && (
        <div className="mt-3 space-y-1.5">
          {c.base_rover.enlaces.map((e) => (
            <div key={e.nome} className="num flex items-center justify-between gap-2 text-[12px]">
              <span className="flex items-center gap-1.5">
                <Badge tone={tomDoEnlace(e)}>{e.nome}</Badge> {rotuloDoEnlace(e)}
              </span>
              <span className="text-muted">{resumoDoEnlace(e)}</span>
            </div>
          ))}
        </div>
      )}
      <div className="mt-3 text-[12px]">
        <Link to="/plataforma/comando/bases" className="text-accent hover:underline">
          Bases da fazenda
        </Link>
      </div>
    </Card>
  )
}

// --- telemetria -----------------------------------------------------------------------

function TelemetriaCard({ painel }: { painel: RoverPanel }) {
  const serie = painel.telemetry
  const saude = painel.health as Record<string, unknown> | null
  const acel = (saude?.accelerator ?? {}) as Record<string, unknown>
  return (
    <Card>
      <CardHeader
        title={
          <span className="flex items-center gap-2">
            <Activity className="size-4" /> Telemetria (2 h)
          </span>
        }
        subtitle={painel.health_reported_at ? `Saúde medida ${fmt.ago(painel.health_reported_at)}.` : 'Sem saúde reportada ainda.'}
      />
      <div className="num mb-3 grid grid-cols-2 gap-2 text-[12px]">
        <span>CPU {saude?.cpu_percent != null ? `${fmt.number(Number(saude.cpu_percent))}%` : '—'}</span>
        <span>memória {saude?.memory_percent != null ? `${fmt.number(Number(saude.memory_percent))}%` : '—'}</span>
        <span>GPU {acel.percent != null ? `${fmt.number(Number(acel.percent))}%` : '—'}</span>
        <span>GPU {acel.temperature_c != null ? `${fmt.number(Number(acel.temperature_c), 1)} °C` : '—'}</span>
        <span>disco {saude?.disk_percent != null ? `${fmt.number(Number(saude.disk_percent))}%` : '—'}</span>
        <span>RTK {serie.at(-1)?.rtk_fix ?? '—'}</span>
      </div>
      {serie.length === 0 ? (
        <div className="text-[13px] text-muted">Sem telemetria nas últimas 2 h.</div>
      ) : (
        <div className="space-y-3">
          <TimeSeries data={serie.map((s) => ({ at: s.t, value: s.battery_percent }))} label="Bateria" unit="%" domain={[0, 100]} height={120} />
          <TimeSeries data={serie.map((s) => ({ at: s.t, value: s.temperature_c }))} label="Temperatura" unit="°C" height={120} />
          <TimeSeries data={serie.map((s) => ({ at: s.t, value: s.speed_ms }))} label="Velocidade" unit="m/s" height={120} />
        </div>
      )}
    </Card>
  )
}

// --- registro de comandos -------------------------------------------------------------

function Registro({ painel, id, pode }: { painel: RoverPanel; id: string; pode: boolean }) {
  const cancelar = useCancelRoverCommand(id)
  return (
    <Card className="overflow-hidden p-0">
      <div className="px-5 pt-4">
        <CardHeader
          title={
            <span className="flex items-center gap-2">
              <RotateCcw className="size-4" /> Registro de comandos
            </span>
          }
          subtitle="Tudo assinado e auditado. Comando não entregue em 2 min expira."
        />
      </div>
      {painel.commands.length === 0 ? (
        <div className="px-5 pb-5 text-[13px] text-muted">Nenhum comando ainda.</div>
      ) : (
        <Table>
          <thead>
            <tr>
              <th className={th}>Quando</th>
              <th className={th}>Comando</th>
              <th className={th}>Estado</th>
              <th className={th}>Resposta</th>
              <th className={th} />
            </tr>
          </thead>
          <tbody>
            {painel.commands.map((c) => {
              const estado = commandState(c.state)
              return (
                <tr key={c.id}>
                  <td className={`${td} num text-[12px]`}>{fmt.ago(c.created_at)}</td>
                  <td className={td}>
                    <div className="font-medium">{commandLabel(c.kind)}</div>
                    <div className="text-[12px] text-muted">{commandSummary(c.kind, c.params)}</div>
                  </td>
                  <td className={td}>
                    <Badge tone={estado.tone}>{estado.label}</Badge>
                  </td>
                  <td className={`${td} num max-w-lg text-[12px] text-ink-2`}>
                    {c.error ?? (c.result ? resumoResposta(c.result) : '—')}
                  </td>
                  <td className={td}>
                    {c.state === 'pendente' && pode && (
                      <Button variant="ghost" onClick={() => cancelar.mutate(c.id)}>
                        Cancelar
                      </Button>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </Table>
      )}
    </Card>
  )
}

function resumoResposta(r: Record<string, unknown>): string {
  if ('pecas' in r) {
    const pecas = r.pecas as Record<string, { ok: boolean }>
    const falhas = Object.entries(pecas).filter(([, v]) => !v.ok).map(([k]) => partLabel(k))
    return falhas.length ? `falhou: ${falhas.join(', ')}` : `${Object.keys(pecas).length} peças OK`
  }
  if ('jpeg_base64' in r) return `foto ${String(r.camera_id ?? '')}`
  return resumoDetalhe(r)
}
