import { BellOff, CheckCheck } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import {
  useMarkAllRead,
  useMarkRead,
  useMyPreferences,
  useNotifications,
  useRolePreferences,
  useSetMyPreference,
  useSetRolePreference,
  type Audience,
} from '@/api/support'
import type { NotificationPreferenceOut, NotificationPreferencesOut } from '@/api/types'
import { Badge, Button, Card, CardHeader, Empty, ErrorBox, Spinner, Table, Tabs, td, th } from '@/components/ui'
import { cn } from '@/lib/cn'
import { fmt } from '@/lib/format'
import {
  deliverySummary,
  groupByDay,
  notificationSeverity,
  notificationTone,
  preferenceBody,
  preferenceSource,
  type PreferenceDraft,
} from '@/lib/notifications'

type Aba = 'avisos' | 'preferencias' | 'papeis'

/**
 * A central de notificações (seção 48), igual nos dois consoles: avisos (lidos e
 * não lidos), as minhas preferências e — para quem pode — o que cada papel recebe.
 */
export function NotificationCenter({
  audience,
  roles,
}: {
  audience: Audience
  /** Papéis cujo padrão esta pessoa pode definir (gestor no cliente; superadmin na plataforma). */
  roles?: { value: string; label: string }[]
}) {
  const [aba, setAba] = useState<Aba>('avisos')
  const abas: { value: Aba; label: string }[] = [
    { value: 'avisos', label: 'Avisos' },
    { value: 'preferencias', label: 'Minhas preferências' },
  ]
  if (roles?.length) abas.push({ value: 'papeis', label: 'Por papel' })

  return (
    <div className="flex flex-col gap-4">
      <Tabs items={abas} value={aba} onChange={setAba} />
      {aba === 'avisos' && <Avisos audience={audience} />}
      {aba === 'preferencias' && <MinhasPreferencias audience={audience} />}
      {aba === 'papeis' && roles?.length && <PreferenciasDoPapel audience={audience} roles={roles} />}
    </div>
  )
}

function Avisos({ audience }: { audience: Audience }) {
  const [soNaoLidas, setSoNaoLidas] = useState(false)
  const lista = useNotifications(audience, { only_unread: soNaoLidas, limit: 200 })
  const marcar = useMarkRead(audience)
  const marcarTodas = useMarkAllRead(audience)
  const navigate = useNavigate()
  const grupos = groupByDay(lista.data ?? [], (iso) => fmt.date(iso))

  return (
    <Card>
      <CardHeader
        title="Avisos"
        subtitle="O que a plataforma avisou a você. Cada aviso nasce de um evento (robô offline, missão bloqueada, chamado respondido…)."
        actions={
          <>
            <label className="flex items-center gap-2 text-[13px]">
              <input type="checkbox" checked={soNaoLidas} onChange={(event) => setSoNaoLidas(event.target.checked)} />
              Só não lidas
            </label>
            <Button
              size="sm"
              icon={<CheckCheck className="size-4" />}
              loading={marcarTodas.isPending}
              onClick={() => marcarTodas.mutate()}
            >
              Marcar todas
            </Button>
          </>
        }
      />
      <ErrorBox error={lista.error ?? marcar.error} className="mx-5 mb-3" />
      {lista.isLoading && <Spinner />}
      {lista.data?.length === 0 && (
        <Empty title="Nenhum aviso" icon={<BellOff className="size-5" />}>
          {soNaoLidas ? 'Tudo lido.' : 'Quando algo acontecer que você escolheu acompanhar, aparece aqui.'}
        </Empty>
      )}
      {grupos.map((grupo) => (
        <div key={grupo.day}>
          <div className="border-y border-line-soft bg-raised px-5 py-1.5 text-[12px] font-medium text-muted">
            {grupo.day}
          </div>
          <ul>
            {grupo.items.map((aviso) => (
              <li key={aviso.id} className={cn('border-b border-line-soft px-5 py-3', !aviso.read_at && 'bg-accent-soft/30')}>
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone={notificationTone(aviso.severity)}>{notificationSeverity(aviso.severity)}</Badge>
                  <span className={cn('text-[14px]', !aviso.read_at && 'font-semibold')}>{aviso.title}</span>
                  <span className="ml-auto text-[12px] text-muted">{fmt.time(aviso.created_at)}</span>
                </div>
                {aviso.body && <p className="mt-1 text-[13px] whitespace-pre-line text-ink-2">{aviso.body}</p>}
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  {aviso.deliveries.map((entrega) => {
                    const resumo = deliverySummary(entrega)
                    return (
                      <Badge key={entrega.channel} tone={resumo.tone}>
                        {resumo.text}
                      </Badge>
                    )
                  })}
                  {aviso.link && (
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => {
                        if (!aviso.read_at) marcar.mutate(aviso.id)
                        navigate(aviso.link!)
                      }}
                    >
                      Abrir
                    </Button>
                  )}
                  {!aviso.read_at && (
                    <Button size="sm" variant="ghost" onClick={() => marcar.mutate(aviso.id)}>
                      Marcar como lida
                    </Button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </Card>
  )
}

function rascunhoDe(pref: NotificationPreferenceOut): PreferenceDraft {
  return { enabled: pref.enabled, email: pref.channels.includes('email'), threshold: pref.threshold ?? null }
}

function TabelaDePreferencias({
  dados,
  salvando,
  onSave,
  onReset,
  mostraOrigem,
}: {
  dados: NotificationPreferencesOut
  salvando: boolean
  onSave: (pref: NotificationPreferenceOut, draft: PreferenceDraft) => void
  onReset?: (pref: NotificationPreferenceOut) => void
  mostraOrigem: boolean
}) {
  const [rascunhos, setRascunhos] = useState<Record<string, PreferenceDraft>>({})
  const email = dados.channels.find((canal) => canal.name === 'email')
  const futuros = dados.channels.filter((canal) => !canal.implemented)

  return (
    <>
      {email && !email.configured && (
        <div className="mx-5 mb-3 rounded-[10px] border border-warning/40 bg-warning/10 px-3.5 py-2.5 text-[13px]">
          O envio por e-mail ainda não está configurado nesta plataforma (SMTP). Os avisos ficam na central e cada um
          mostra “E-mail: não enviado”, com o motivo.
        </div>
      )}
      <Table>
        <thead>
          <tr>
            <th className={th}>Aviso</th>
            <th className={th}>Receber</th>
            <th className={th}>Por e-mail</th>
            <th className={th}>Limite</th>
            {mostraOrigem && <th className={th}>Origem</th>}
            <th className={th} />
          </tr>
        </thead>
        <tbody>
          {dados.preferences.map((pref) => {
            const atual = rascunhos[pref.kind] ?? rascunhoDe(pref)
            const mudou = JSON.stringify(atual) !== JSON.stringify(rascunhoDe(pref))
            const muda = (parcial: Partial<PreferenceDraft>) =>
              setRascunhos((antes) => ({ ...antes, [pref.kind]: { ...atual, ...parcial } }))
            return (
              <tr key={pref.kind}>
                <td className={td}>
                  <div className="font-medium">{pref.label}</div>
                  <div className="text-[12px] text-muted">{pref.description}</div>
                </td>
                <td className={td}>
                  <input
                    type="checkbox"
                    aria-label={`Receber: ${pref.label}`}
                    checked={atual.enabled}
                    onChange={(event) => muda({ enabled: event.target.checked })}
                  />
                </td>
                <td className={td}>
                  <input
                    type="checkbox"
                    aria-label={`E-mail: ${pref.label}`}
                    checked={atual.enabled && atual.email}
                    disabled={!atual.enabled}
                    onChange={(event) => muda({ email: event.target.checked })}
                  />
                </td>
                <td className={td}>
                  {pref.threshold_unit ? (
                    <span className="flex items-center gap-1">
                      <input
                        className="input h-8 w-20"
                        type="number"
                        min={0}
                        max={100}
                        step={0.5}
                        value={atual.threshold ?? ''}
                        onChange={(event) =>
                          muda({ threshold: event.target.value === '' ? null : Number(event.target.value) })
                        }
                      />
                      {pref.threshold_unit}
                    </span>
                  ) : (
                    <span className="text-muted">—</span>
                  )}
                </td>
                {mostraOrigem && <td className={cn(td, 'text-[12px] text-muted')}>{preferenceSource(pref.source)}</td>}
                <td className={cn(td, 'whitespace-nowrap')}>
                  <Button
                    size="sm"
                    variant={mudou ? 'primary' : 'ghost'}
                    disabled={!mudou}
                    loading={salvando && mudou}
                    onClick={() => onSave(pref, atual)}
                  >
                    Salvar
                  </Button>
                  {onReset && pref.source !== 'padrao' && (
                    <Button size="sm" variant="ghost" onClick={() => onReset(pref)}>
                      Voltar ao padrão
                    </Button>
                  )}
                </td>
              </tr>
            )
          })}
        </tbody>
      </Table>
      {futuros.length > 0 && (
        <p className="px-5 py-3 text-[12px] text-muted">
          Ainda não disponíveis: {futuros.map((canal) => canal.label).join(', ')}. A plataforma já tem o lugar para
          eles; a integração vem depois.
        </p>
      )}
    </>
  )
}

function MinhasPreferencias({ audience }: { audience: Audience }) {
  const prefs = useMyPreferences(audience)
  const salvar = useSetMyPreference(audience)
  return (
    <Card>
      <CardHeader
        title="Minhas preferências"
        subtitle="O que você recebe e por onde. A central do console recebe sempre que o aviso está ligado."
      />
      <ErrorBox error={prefs.error ?? salvar.error} className="mx-5 mb-3" />
      {prefs.isLoading && <Spinner />}
      {prefs.data && (
        <TabelaDePreferencias
          key={JSON.stringify(prefs.data.preferences)}
          dados={prefs.data}
          salvando={salvar.isPending}
          mostraOrigem
          onSave={(pref, draft) => salvar.mutate(preferenceBody(pref.kind, draft, Boolean(pref.threshold_unit)))}
          onReset={(pref) => salvar.mutate({ kind: pref.kind, reset: true })}
        />
      )}
    </Card>
  )
}

function PreferenciasDoPapel({ audience, roles }: { audience: Audience; roles: { value: string; label: string }[] }) {
  const [papel, setPapel] = useState(roles[0]?.value ?? '')
  const prefs = useRolePreferences(audience, papel)
  const salvar = useSetRolePreference(audience)
  return (
    <Card>
      <CardHeader
        title="O que cada papel recebe"
        subtitle="Vale para todos com o papel, salvo quem escolheu diferente para si."
        actions={
          <select className="input h-9" value={papel} onChange={(event) => setPapel(event.target.value)} aria-label="Papel">
            {roles.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
        }
      />
      <ErrorBox error={prefs.error ?? salvar.error} className="mx-5 mb-3" />
      {prefs.isLoading && <Spinner />}
      {prefs.data && (
        <TabelaDePreferencias
          key={`${papel}:${JSON.stringify(prefs.data.preferences)}`}
          dados={prefs.data}
          salvando={salvar.isPending}
          mostraOrigem={false}
          onSave={(pref, draft) =>
            salvar.mutate({ role: papel, ...preferenceBody(pref.kind, draft, Boolean(pref.threshold_unit)) })
          }
          onReset={(pref) => salvar.mutate({ role: papel, kind: pref.kind, reset: true })}
        />
      )}
    </Card>
  )
}
