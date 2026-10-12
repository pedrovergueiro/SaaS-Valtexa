/**
 * Abas de Configurações sobre a própria conta do cliente: "Meu plano", "Dados
 * no treino" e "Acessos da ValTexa" (brief, seções 29, 31 e 32).
 *
 * Tudo vem das rotas `/v1/tenants/current/*`, que o servidor filtra pelo cliente
 * do token. Quem pode mudar o consentimento é só o dono (`tenant:manage`); o
 * servidor confere de novo.
 */
import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, CheckCircle2, ShieldCheck } from 'lucide-react'
import { useState } from 'react'

import { api } from '@/api/client'
import { useApiMutation } from '@/api/queries'
import { useAuth } from '@/auth/AuthProvider'
import { Badge, Button, Card, CardHeader, Empty, ErrorBox, Meter, Spinner, Table, td, th, useToast } from '@/components/ui'
import {
  consentSourceLabel,
  consentSummary,
  featureLabel,
  planSituation,
  supportModeLabel,
  supportSessionStatus,
  usageAlerts,
  usageText,
  type ConsentStatus,
  type MyPlan,
  type TenantSupportSession,
} from '@/lib/account'
import { fmt } from '@/lib/format'

const accountKeys = {
  plan: ['tenant', 'plan'] as const,
  consent: ['tenant', 'data-consent'] as const,
  support: ['tenant', 'support-sessions'] as const,
}

export function MyPlanPanel() {
  const plano = useQuery({ queryKey: accountKeys.plan, queryFn: () => api<MyPlan>('/v1/tenants/current/plan') })
  const data = plano.data
  return (
    <Card>
      <CardHeader
        title="Meu plano"
        subtitle="O que o plano contratado inclui e quanto já foi usado. Para mudar de plano, fale com a ValTexa."
      />
      <ErrorBox error={plano.error} className="mx-5 mb-4" />
      {plano.isLoading && <Spinner />}
      {data && <PlanBody plan={data} />}
    </Card>
  )
}

function PlanBody({ plan }: { plan: MyPlan }) {
  const situacao = planSituation(plan)
  const alertas = usageAlerts(plan.usage)
  if (!plan.has_subscription) {
    return (
      <Empty title="Sem plano contratado" icon={<ShieldCheck className="size-5" />}>
        Esta conta ainda não tem plano: nenhum limite é aplicado. Próximo passo: combinar o plano com a ValTexa.
      </Empty>
    )
  }
  return (
    <div className="flex flex-col gap-5 px-5 pb-5">
      <div className="flex flex-wrap items-center gap-3">
        <div className="font-display text-[20px] font-semibold">{plan.plan?.name ?? '—'}</div>
        <Badge tone={situacao.tone}>{situacao.label}</Badge>
        {plan.ends_at && <span className="text-[13px] text-muted">até {fmt.date(plan.ends_at)}</span>}
      </div>
      {plan.plan?.description && <p className="text-[13px] text-ink-2">{plan.plan.description}</p>}
      {alertas.length > 0 && (
        <ul className="flex flex-col gap-2" aria-label="Avisos de uso">
          {alertas.map((alerta) => (
            <li key={alerta.resource} className="flex items-start gap-2 text-[13px]">
              <AlertTriangle
                className={alerta.tone === 'critical' ? 'mt-0.5 size-4 shrink-0 text-critical' : 'mt-0.5 size-4 shrink-0 text-warning'}
                aria-hidden
              />
              {alerta.text}
            </li>
          ))}
        </ul>
      )}
      <Table>
        <thead>
          <tr>
            <th className={th}>Recurso</th>
            <th className={th}>Uso</th>
            <th className={`${th} w-1/3`} />
          </tr>
        </thead>
        <tbody>
          {plan.usage.map((item) => (
            <tr key={item.resource}>
              <td className={td}>{item.label}</td>
              <td className={`${td} num`}>{usageText(item)}</td>
              <td className={td}>
                {item.percent !== null && item.percent !== undefined && (
                  <Meter
                    value={item.percent / 100}
                    tone={item.percent >= 100 ? 'critical' : item.percent >= 80 ? 'warning' : 'accent'}
                    label={`${item.label}: ${Math.round(item.percent)} %`}
                  />
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </Table>
      <div>
        <div className="mb-2 text-[13px] font-medium">Funcionalidades incluídas</div>
        {(plan.plan?.features ?? []).length === 0 ? (
          <div className="text-[13px] text-muted">Nenhuma funcionalidade extra neste plano.</div>
        ) : (
          <div className="flex flex-wrap gap-2">
            {(plan.plan?.features ?? []).map((code) => (
              <Badge key={code} tone="good">
                {featureLabel(code)}
              </Badge>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

export function DataConsentPanel() {
  const { can } = useAuth()
  const toast = useToast()
  const status = useQuery({
    queryKey: accountKeys.consent,
    queryFn: () => api<ConsentStatus>('/v1/tenants/current/data-consent'),
  })
  const [escolha, setEscolha] = useState<'sim' | 'nao' | null>(null)
  const [nota, setNota] = useState('')
  const salvar = useApiMutation(
    (body: { allowed: boolean; notes: string | null }) =>
      api<ConsentStatus>('/v1/tenants/current/data-consent', { method: 'PUT', body }),
    [accountKeys.consent],
  )
  const dono = can('tenant:manage')
  const data = status.data
  const atual = data ? (data.allowed ? 'sim' : 'nao') : null
  const marcado = escolha ?? (data?.decided ? atual : null)

  async function registrar() {
    if (!marcado) return
    await salvar.mutateAsync({ allowed: marcado === 'sim', notes: nota.trim() || null })
    setEscolha(null)
    setNota('')
    toast.push({ tone: 'good', title: 'Decisão registrada.', detail: 'Vale a partir de agora, com o seu nome e o horário.' })
  }

  return (
    <Card>
      <CardHeader
        title="Uso dos dados no treino"
        subtitle="Permitir a utilização dos dados e imagens desta conta para melhoria dos modelos da ValTexa? Nunca é automático: sem resposta, vale NÃO."
      />
      <ErrorBox error={status.error ?? salvar.error} className="mx-5 mb-4" />
      {status.isLoading && <Spinner />}
      {data && (
        <div className="flex flex-col gap-5 px-5 pb-5">
          <div className="flex items-start gap-2 text-[14px]">
            {data.allowed ? (
              <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-good" aria-hidden />
            ) : (
              <ShieldCheck className="mt-0.5 size-4 shrink-0 text-ink-2" aria-hidden />
            )}
            <span>{consentSummary(data)}</span>
          </div>
          {dono ? (
            <fieldset className="flex flex-col gap-3">
              <legend className="mb-2 text-[13px] font-medium">Sua decisão</legend>
              <label className="flex items-center gap-2 text-[14px]">
                <input type="radio" name="consent" checked={marcado === 'sim'} onChange={() => setEscolha('sim')} />
                SIM — permitir o uso para melhorar os modelos
              </label>
              <label className="flex items-center gap-2 text-[14px]">
                <input type="radio" name="consent" checked={marcado === 'nao'} onChange={() => setEscolha('nao')} />
                NÃO — não usar os dados desta conta no treino
              </label>
              {marcado === 'nao' && data.allowed && (
                <p className="text-[12px] text-muted">
                  Ao trocar para NÃO, as imagens ainda não usadas saem do treino. Modelos já treinados não são refeitos.
                </p>
              )}
              <input
                className="input"
                placeholder="Observação (opcional)"
                value={nota}
                maxLength={2000}
                onChange={(event) => setNota(event.target.value)}
                aria-label="Observação sobre a decisão"
              />
              <div>
                <Button
                  variant="primary"
                  disabled={!marcado || (data.decided && marcado === atual) || salvar.isPending}
                  onClick={registrar}
                >
                  Registrar decisão
                </Button>
              </div>
            </fieldset>
          ) : (
            <p className="text-[13px] text-muted">Só o proprietário da conta pode mudar esta decisão.</p>
          )}
          {data.history.length > 0 && (
            <div>
              <div className="mb-2 text-[13px] font-medium">Histórico</div>
              <Table>
                <thead>
                  <tr>
                    <th className={th}>Quando</th>
                    <th className={th}>Decisão</th>
                    <th className={th}>Quem</th>
                    <th className={th}>Origem</th>
                  </tr>
                </thead>
                <tbody>
                  {data.history.map((linha) => (
                    <tr key={linha.id}>
                      <td className={`${td} num`}>{fmt.dateTime(linha.decided_at)}</td>
                      <td className={td}>
                        <Badge tone={linha.allowed ? 'good' : 'neutral'}>{linha.allowed ? 'SIM' : 'NÃO'}</Badge>
                      </td>
                      <td className={td}>{linha.decided_by_label}</td>
                      <td className={`${td} text-ink-2`}>
                        {consentSourceLabel(linha.source)}
                        {linha.document_ref && ` · ${linha.document_ref}`}
                        {linha.notes && <div className="text-[12px] text-muted">{linha.notes}</div>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </div>
          )}
        </div>
      )}
    </Card>
  )
}

export function SupportAccessPanel() {
  const { can } = useAuth()
  const permitido = can('audit:read')
  const sessoes = useQuery({
    queryKey: accountKeys.support,
    queryFn: () => api<TenantSupportSession[]>('/v1/tenants/current/support-sessions'),
    enabled: permitido,
  })
  return (
    <Card>
      <CardHeader
        title="Acessos da ValTexa"
        subtitle="Toda vez que alguém da equipe da ValTexa entrou nesta conta: quem, quando, por quê, em que modo e quantas ações fez. Nunca há acesso silencioso."
      />
      {!permitido && (
        <p className="px-5 pb-5 text-[13px] text-muted">Seu papel não inclui a leitura da auditoria desta conta.</p>
      )}
      <ErrorBox error={sessoes.error} className="mx-5 mb-4" />
      {sessoes.isLoading && permitido && <Spinner />}
      {sessoes.data?.length === 0 && (
        <Empty title="A equipe da ValTexa nunca entrou nesta conta" icon={<ShieldCheck className="size-5" />}>
          Quando alguém entrar para dar suporte, a entrada aparece aqui, com o motivo.
        </Empty>
      )}
      {(sessoes.data?.length ?? 0) > 0 && (
        <Table>
          <thead>
            <tr>
              <th className={th}>Quando</th>
              <th className={th}>Quem</th>
              <th className={th}>Motivo</th>
              <th className={th}>Modo</th>
              <th className={th}>Ações</th>
              <th className={th}>Situação</th>
            </tr>
          </thead>
          <tbody>
            {sessoes.data?.map((sessao) => (
              <tr key={sessao.id}>
                <td className={`${td} num`}>
                  {fmt.dateTime(sessao.started_at)}
                  {sessao.ended_at && <div className="text-[12px] text-muted">até {fmt.time(sessao.ended_at)}</div>}
                </td>
                <td className={td}>{sessao.user_email ?? '—'}</td>
                <td className={td}>
                  {sessao.reason}
                  {sessao.ticket_ref && <div className="text-[12px] text-muted">Chamado {sessao.ticket_ref}</div>}
                </td>
                <td className={td}>
                  <Badge tone={sessao.mode === 'assistido' ? 'warning' : 'info'}>{supportModeLabel(sessao.mode)}</Badge>
                  {sessao.assisted_reason && <div className="text-[12px] text-muted">{sessao.assisted_reason}</div>}
                </td>
                <td className={`${td} num`}>{sessao.request_count}</td>
                <td className={td}>
                  <Badge tone={sessao.is_open ? 'warning' : 'neutral'} pulse={sessao.is_open}>
                    {supportSessionStatus(sessao)}
                  </Badge>
                </td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
    </Card>
  )
}
