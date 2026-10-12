/**
 * Peças da tela de Observabilidade, usadas pelo console da plataforma e pelo do
 * cliente: saúde da frota, alertas (com "reconhecer") e regras (com edição).
 *
 * O que muda entre os dois consoles é o `scope` (rotas `/v1/platform/observability`
 * ou `/v1/observability`) e o que a pessoa pode — o servidor confere de novo.
 */
import { BellOff, Bot, CheckCheck, Pencil } from 'lucide-react'
import { useState } from 'react'

import { Badge, Button, Empty, ErrorBox, FormField, Modal, Table, td, th } from '@/components/ui'
import { fmt } from '@/lib/format'
import {
  alertStateLabel,
  alertTone,
  pct,
  roverIssues,
  ruleThreshold,
  severityLabel,
  sortAlerts,
  usageTone,
  useAckAlert,
  useResetRule,
  useSaveRule,
  type AlertRule,
  type ObsAlert,
  type RoverHealth,
} from '@/lib/observability'

type Scope = 'plataforma' | 'cliente'

export function FleetHealthTable({ rovers, showTenant = false }: { rovers: RoverHealth[]; showTenant?: boolean }) {
  if (rovers.length === 0) {
    return (
      <Empty title="Nenhum robô" icon={<Bot className="size-5" />}>
        A saúde aparece quando o robô manda a primeira telemetria.
      </Empty>
    )
  }
  return (
    <Table>
      <thead>
        <tr>
          <th className={th}>Robô</th>
          <th className={th}>Computador</th>
          <th className={th}>Disco, temperatura, bateria</th>
          <th className={th}>Câmeras e sensores</th>
          <th className={th}>Rede e sincronização</th>
          <th className={th}>Versões</th>
        </tr>
      </thead>
      <tbody>
        {rovers.map((r) => {
          const problemas = roverIssues(r)
          return (
            <tr key={r.device_id}>
              <td className={td}>
                <div className="font-medium">{r.name}</div>
                <div className="num text-[12px] text-muted">
                  {r.serial_number}
                  {showTenant && r.tenant_name ? ` · ${r.tenant_name}` : ''}
                </div>
                {problemas.length > 0 ? (
                  <div className="mt-1 max-w-60 text-[12px] text-serious">{problemas.join('; ')}</div>
                ) : (
                  <div className="mt-1 text-[12px] text-good">sem problema</div>
                )}
                {r.open_alerts > 0 && (
                  <Badge tone="warning" className="mt-1">
                    {r.open_alerts} alerta(s) aberto(s)
                  </Badge>
                )}
                {r.simulated.length > 0 && (
                  <div className="mt-1 text-[11px] text-muted">simulado: {r.simulated.join(', ')}</div>
                )}
              </td>
              <td className={`${td} num text-[12px]`}>
                <div>CPU {pct(r.cpu_percent)}</div>
                <div>memória {pct(r.memory_percent)}</div>
                <div>
                  {r.accelerator_name ?? 'acelerador'} {pct(r.accelerator_percent)}
                </div>
              </td>
              <td className={`${td} text-[12px]`}>
                <Badge tone={usageTone(r.disk_percent, 90)}>disco {pct(r.disk_percent, 1)}</Badge>
                <div className="num mt-1">
                  {r.temperature_c != null ? `${fmt.number(r.temperature_c, 1)} °C` : 'temperatura não medida'}
                </div>
                <div className="num">bateria {pct(r.battery_percent)}</div>
              </td>
              <td className={`${td} text-[12px]`}>
                <div>
                  {r.cameras_total ? `${r.cameras_ok} de ${r.cameras_total} câmera(s) ok` : 'câmeras não informadas'}
                </div>
                <div className="text-muted">
                  {Object.entries(r.sensors)
                    .filter(([, v]) => v)
                    .map(([k, v]) => `${k}: ${v === 'nao_monitorado' ? 'não monitorado' : v}`)
                    .join(' · ') || 'sensores não informados'}
                </div>
              </td>
              <td className={`${td} text-[12px]`}>
                <Badge tone={r.connectivity === 'offline' ? 'critical' : r.connectivity === 'degraded' ? 'warning' : 'good'}>
                  {r.connectivity === 'offline' ? 'sem comunicação' : r.connectivity === 'degraded' ? 'instável' : 'conectado'}
                </Badge>
                <div className="mt-1">visto {fmt.ago(r.last_seen_at)}</div>
                <div className="text-muted">
                  {r.sync_pending} pendente(s) · sincronizou {r.last_sync_at ? fmt.ago(r.last_sync_at) : 'sem dado'}
                </div>
              </td>
              <td className={`${td} num text-[12px] text-ink-2`}>
                <div>runtime {r.versions.runtime ?? '—'}</div>
                <div>edge {r.versions.edge_ai ?? '—'}</div>
                <div>modelo {r.versions.model ?? '—'}</div>
              </td>
            </tr>
          )
        })}
      </tbody>
    </Table>
  )
}

export function AlertsTable({
  alerts,
  scope,
  canAck,
  showTenant = false,
}: {
  alerts: ObsAlert[]
  scope: Scope
  canAck: boolean
  showTenant?: boolean
}) {
  const [alvo, setAlvo] = useState<ObsAlert | null>(null)
  if (alerts.length === 0) {
    return (
      <Empty title="Nenhum alerta" icon={<BellOff className="size-5" />}>
        Quando uma regra disparar, ela aparece aqui e chega pelas notificações.
      </Empty>
    )
  }
  return (
    <>
      <Table>
        <thead>
          <tr>
            <th className={th}>Situação</th>
            <th className={th}>Alerta</th>
            <th className={th}>Quando</th>
            <th className={th}>Quem cuida</th>
          </tr>
        </thead>
        <tbody>
          {sortAlerts(alerts).map((a) => (
            <tr key={a.id}>
              <td className={td}>
                <Badge tone={alertTone(a)} pulse={a.state === 'disparado' && a.severity === 'critico'}>
                  {alertStateLabel(a.state)}
                </Badge>
                <div className="mt-1 text-[12px] text-muted">{severityLabel(a.severity)}</div>
              </td>
              <td className={td}>
                <div className="font-medium">
                  {a.kind_label}: {a.subject_label}
                </div>
                {showTenant && a.tenant_name && <div className="text-[12px] text-muted">{a.tenant_name}</div>}
                <div className="mt-0.5 max-w-xl text-[13px] text-ink-2">{a.message}</div>
              </td>
              <td className={`${td} text-[12px] whitespace-nowrap`}>
                <div>disparou {fmt.dateTime(a.fired_at)}</div>
                {a.resolved_at ? (
                  <div className="text-good">resolveu {fmt.dateTime(a.resolved_at)}</div>
                ) : (
                  <div className="text-muted">última leitura {fmt.ago(a.last_seen_at)}</div>
                )}
              </td>
              <td className={`${td} text-[12px]`}>
                {a.acknowledged_label ? (
                  <>
                    <div>{a.acknowledged_label}</div>
                    {a.ack_note && <div className="text-muted">“{a.ack_note}”</div>}
                  </>
                ) : a.state === 'disparado' && canAck ? (
                  <Button size="sm" icon={<CheckCheck className="size-4" />} onClick={() => setAlvo(a)}>
                    Reconhecer
                  </Button>
                ) : (
                  <span className="text-muted">—</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </Table>
      {alvo && <AckModal alert={alvo} scope={scope} onClose={() => setAlvo(null)} />}
    </>
  )
}

function AckModal({ alert, scope, onClose }: { alert: ObsAlert; scope: Scope; onClose: () => void }) {
  const [nota, setNota] = useState('')
  const ack = useAckAlert(scope)
  return (
    <Modal open onClose={onClose} title="Reconhecer alerta">
      <p className="text-[13px] text-ink-2">
        {alert.kind_label}: {alert.subject_label}. Reconhecer diz que alguém está cuidando — o alerta continua aberto até a
        condição passar.
      </p>
      <FormField label="Nota (opcional)">
        <textarea className="input min-h-20" value={nota} onChange={(e) => setNota(e.target.value)} maxLength={2000} />
      </FormField>
      <ErrorBox error={ack.error} />
      <div className="mt-2 flex justify-end gap-2">
        <Button variant="ghost" onClick={onClose}>
          Cancelar
        </Button>
        <Button
          variant="primary"
          loading={ack.isPending}
          onClick={() => ack.mutate({ id: alert.id, note: nota.trim() }, { onSuccess: onClose })}
        >
          Reconhecer
        </Button>
      </div>
    </Modal>
  )
}

export function RulesTable({ rules, scope, canEdit }: { rules: AlertRule[]; scope: Scope; canEdit: boolean }) {
  const [alvo, setAlvo] = useState<AlertRule | null>(null)
  const reset = useResetRule()
  return (
    <>
      <Table>
        <thead>
          <tr>
            <th className={th}>Regra</th>
            <th className={th}>Limite</th>
            <th className={th}>Severidade</th>
            <th className={th}>Origem</th>
            {canEdit && <th className={th} />}
          </tr>
        </thead>
        <tbody>
          {rules.map((r) => (
            <tr key={r.kind}>
              <td className={td}>
                <div className="font-medium">
                  {r.label} {!r.enabled && <Badge tone="neutral">desligada</Badge>}
                </div>
                <div className="max-w-lg text-[12px] text-muted">{r.description}</div>
              </td>
              <td className={`${td} num text-[13px]`}>{ruleThreshold(r)}</td>
              <td className={td}>
                <Badge tone={r.severity === 'critico' ? 'critical' : 'warning'}>{severityLabel(r.severity)}</Badge>
              </td>
              <td className={`${td} text-[12px]`}>
                {r.source === 'cliente' ? (
                  <>
                    <div>própria deste cliente</div>
                    <div className="text-muted">
                      padrão:{' '}
                      {ruleThreshold({ threshold: r.default_threshold, unit: r.unit, window_minutes: r.window_minutes })}
                    </div>
                  </>
                ) : (
                  <span className="text-muted">padrão da plataforma</span>
                )}
              </td>
              {canEdit && (
                <td className={`${td} whitespace-nowrap`}>
                  <Button size="sm" variant="ghost" icon={<Pencil className="size-4" />} onClick={() => setAlvo(r)}>
                    Ajustar
                  </Button>
                  {scope === 'cliente' && r.source === 'cliente' && (
                    <Button size="sm" variant="ghost" loading={reset.isPending} onClick={() => reset.mutate(r.kind)}>
                      Voltar ao padrão
                    </Button>
                  )}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </Table>
      <ErrorBox error={reset.error} className="m-4" />
      {alvo && <RuleModal rule={alvo} scope={scope} onClose={() => setAlvo(null)} />}
    </>
  )
}

function RuleModal({ rule, scope, onClose }: { rule: AlertRule; scope: Scope; onClose: () => void }) {
  const [ligada, setLigada] = useState(rule.enabled)
  const [limite, setLimite] = useState(rule.threshold != null ? String(rule.threshold) : '')
  const [janela, setJanela] = useState(rule.window_minutes != null ? String(rule.window_minutes) : '')
  const [severidade, setSeveridade] = useState(rule.severity)
  const salvar = useSaveRule(scope)
  const enviar = () => {
    const body: Record<string, unknown> = { enabled: ligada, severity: severidade }
    if (rule.threshold != null && limite.trim()) body.threshold = Number(limite.replace(',', '.'))
    if (rule.window_minutes != null && janela.trim()) body.window_minutes = Number(janela)
    salvar.mutate({ kind: rule.kind, body }, { onSuccess: onClose })
  }
  return (
    <Modal open onClose={onClose} title={`Ajustar: ${rule.label}`}>
      <p className="text-[13px] text-ink-2">
        {scope === 'cliente'
          ? 'Vale só para os robôs deste cliente. "Voltar ao padrão" desfaz.'
          : 'É a regra padrão: vale para todos os clientes que não têm versão própria.'}
      </p>
      <label className="flex items-center gap-2 text-[13px]">
        <input type="checkbox" checked={ligada} onChange={(e) => setLigada(e.target.checked)} /> Regra ligada
      </label>
      {rule.threshold != null && (
        <FormField label={`Limite${rule.unit ? ` (${rule.unit})` : ''}`}>
          <input className="input" inputMode="decimal" value={limite} onChange={(e) => setLimite(e.target.value)} />
        </FormField>
      )}
      {rule.window_minutes != null && (
        <FormField label="Janela (minutos)">
          <input className="input" inputMode="numeric" value={janela} onChange={(e) => setJanela(e.target.value)} />
        </FormField>
      )}
      <FormField label="Severidade">
        <select className="input" value={severidade} onChange={(e) => setSeveridade(e.target.value)}>
          <option value="aviso">Aviso</option>
          <option value="critico">Crítico</option>
        </select>
      </FormField>
      <ErrorBox error={salvar.error} />
      <div className="mt-2 flex justify-end gap-2">
        <Button variant="ghost" onClick={onClose}>
          Cancelar
        </Button>
        <Button variant="primary" loading={salvar.isPending} onClick={enviar}>
          Salvar
        </Button>
      </div>
    </Modal>
  )
}
