import { useState } from 'react'

import { useAuth } from '@/auth/AuthProvider'
import { AlertsTable, FleetHealthTable, RulesTable } from '@/components/Observability'
import { Card, CardHeader, ErrorBox, PageHeader, Spinner, Tabs } from '@/components/ui'
import { alertCounts, useAlertRules, useFleetHealth, useObsAlerts } from '@/lib/observability'

type Aba = 'frota' | 'alertas' | 'regras'

/**
 * Observabilidade do cliente (Parte 7): **só o que é dele** — a saúde dos robôs
 * dele, os alertas desses robôs e as regras de robô (com a versão própria, se o
 * gestor ajustou). Nada da API, da IA nem de outro cliente: isso é do console da
 * plataforma.
 */
export default function Observability() {
  const { can } = useAuth()
  const [aba, setAba] = useState<Aba>('frota')
  const frota = useFleetHealth('cliente')
  const alertas = useObsAlerts('cliente')
  const regras = useAlertRules('cliente')
  const gerencia = can('device:manage')
  const contagem = alertCounts(alertas.data ?? [])
  return (
    <>
      <PageHeader
        title="Saúde da frota"
        subtitle="Computador, disco, temperatura, bateria, câmeras, conexão e sincronização de cada robô, e os alertas deles. Atualiza a cada 30 s."
      />
      <div className="mb-4">
        <Tabs<Aba>
          value={aba}
          onChange={setAba}
          items={[
            { value: 'frota', label: 'Robôs', count: frota.data?.length },
            { value: 'alertas', label: 'Alertas', count: contagem.open },
            { value: 'regras', label: 'Regras' },
          ]}
        />
      </div>
      {aba === 'frota' && (
        <Card className="overflow-hidden p-0">
          <ErrorBox error={frota.error} className="m-4" />
          {frota.isLoading && <Spinner />}
          {frota.data && <FleetHealthTable rovers={frota.data} />}
        </Card>
      )}
      {aba === 'alertas' && (
        <Card className="overflow-hidden p-0">
          <CardHeader
            title="Alertas dos seus robôs"
            subtitle="Disparam sozinhos e resolvem sozinhos quando a condição passa. Reconhecer diz à equipe que alguém está cuidando."
          />
          <ErrorBox error={alertas.error} className="m-4" />
          {alertas.isLoading && <Spinner />}
          {alertas.data && <AlertsTable alerts={alertas.data} scope="cliente" canAck={gerencia} />}
        </Card>
      )}
      {aba === 'regras' && (
        <Card className="overflow-hidden p-0">
          <CardHeader
            title="Regras dos alertas"
            subtitle={
              gerencia
                ? 'Ajuste o limite para os seus robôs; o restante da plataforma segue o padrão.'
                : 'Só o gestor ou o técnico ajusta as regras.'
            }
          />
          <ErrorBox error={regras.error} className="m-4" />
          {regras.isLoading && <Spinner />}
          {regras.data && <RulesTable rules={regras.data} scope="cliente" canEdit={gerencia} />}
        </Card>
      )}
    </>
  )
}
