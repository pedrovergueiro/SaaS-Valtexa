import { AlertTriangle, Check, Compass, Route, ShieldCheck, Timer, Zap } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import {
  useCreateMission,
  useDeviceModels,
  useDevices,
  usePlanField,
} from '@/api/queries'
import { useToolFields } from '@/platform/api'
import type { PlanOut, TerrainObjectOut } from '@/api/types'
import { FarmMap, PlanLegend } from '@/components/FarmMap'
import {
  Badge,
  Button,
  Card,
  CardHeader,
  Empty,
  ErrorBox,
  FormField,
  PageHeader,
  Stat,
  Table,
  td,
  th,
} from '@/components/ui'
import { fmt } from '@/lib/format'
import { terrainKind } from '@/lib/labels'

/**
 * Gerar missão.
 *
 * Fecha o caminho entre "o talhão está desenhado" e "o rover tem uma missão":
 * calcula a rota, o tempo, a energia e onde faltará bateria, desenha tudo no
 * mapa e só então oferece o botão que cria a missão.
 *
 * **Planejar não escreve nada.** O mesmo talhão é replanejado dezenas de vezes
 * enquanto se escolhe a direção das linhas e a largura da faixa; nenhuma dessas
 * tentativas toca o banco. Quem escreve é o botão de gerar, e ele só aparece
 * depois que há plano na tela.
 *
 * **A validação é humana e é obrigatória.** A missão nasce em rascunho, sem
 * assinatura e sem valer nada no mundo físico — o caminho até o robô ainda
 * passa por aprovação e pela camada de segurança. Esta tela mostra o que
 * precisa ser conferido antes disso: por onde o rover passa, onde ele para para
 * carregar, e o que a leitura de imagem marcou como bloqueio.
 *
 * **A rota contorna os obstáculos.** Cada passada que atravessaria uma mata é
 * partida em duas, uma de cada lado, com folga. O plano sai com mais passadas e
 * menos metros de linha — que é o que acontece no campo, e é o motivo de o plano
 * com obstáculo ser o confiável: o sem obstáculo conta como lavoura o chão que é
 * mata.
 *
 * O obstáculo só chega aqui se alguém já rodou o encaixe de contorno no editor
 * do talhão. Sem leitura de imagem, o plano varre o talhão inteiro e diz isso.
 */
export default function MissionPlanner() {
  const navigate = useNavigate()
  const talhoes = useToolFields()
  const modelos = useDeviceModels()
  const frota = useDevices()

  const [fieldId, setFieldId] = useState('')
  const [modelo, setModelo] = useState('ROVER_V3')
  const [azimute, setAzimute] = useState('90')
  const [faixa, setFaixa] = useState('')
  const [bateria, setBateria] = useState('100')
  const [margem, setMargem] = useState('2')
  const [plano, setPlano] = useState<PlanOut | null>(null)
  const [deviceId, setDeviceId] = useState('')

  const planejar = usePlanField(fieldId)
  const criar = useCreateMission()

  const campo = useMemo(
    () => (talhoes.data ?? []).find((item) => item.id === fieldId),
    [talhoes.data, fieldId],
  )
  const semContorno = Boolean(campo && (campo.boundary?.length ?? 0) < 3)
  const rovers = (frota.data ?? []).filter((item) => item.kind === 'rover')

  // Os obstáculos vêm do plano, que os lê do talhão. Antes de calcular, do
  // próprio talhão: quem abre a tela já vê o que a última leitura achou, sem
  // precisar apertar nada.
  const terreno = plano?.terrain ?? campo?.terrain ?? null
  const obstaculos: TerrainObjectOut[] = terreno?.resolution_ok
    ? (terreno.objects ?? [])
    : []

  async function calcular() {
    setPlano(null)
    const resultado = await planejar.mutateAsync({
      device_model_code: modelo,
      row_azimuth_deg: Number(azimute) || 0,
      swath_m: faixa ? Number(faixa) : null,
      start_battery_percent: Number(bateria) || 100,
      reserve_percent: null,
      speed_ms: null,
      obstacle_margin_m: Number(margem) || 0,
    })
    setPlano(resultado)
  }

  async function gerarMissao() {
    if (!plano || !deviceId) return
    const missao = await criar.mutateAsync({
      kind: 'scout',
      field_id: fieldId,
      device_id: deviceId,
      zone_id: null,
      target_polygon: null,
      // O plano viaja junto com a missão: quem a validar depois precisa ver os
      // mesmos números que apareceram aqui, e não recalculá-los.
      plan: {
        origem: 'admin/planejamento',
        device_model_code: plano.device_model_code,
        azimute_deg: plano.azimute_deg,
        swath_m: plano.swath_m,
        passadas: plano.passadas,
        metros_totais: plano.metros_totais,
        minutos_totais: plano.minutos_totais,
        wh_totais: plano.wh_totais,
        cargas: plano.cargas,
        postes: plano.postes,
        perfil_medido: plano.perfil_medido,
        obstaculos_contornados: plano.avoided,
        area_contornada_ha: plano.area_contornada_ha,
      },
      product_id: null,
      product_batch_id: null,
      tank_id: null,
      authorized_rate_l_ha: null,
      authorized_quantity_l: null,
      decision_id: null,
    })
    navigate(`/missoes/${missao.id}`)
  }

  return (
    <>
      <PageHeader
        title="Gerar missão"
        subtitle="Rota, tempo, energia e postes de recarga. Nada é gravado até você confirmar."
      />

      <ErrorBox error={planejar.error ?? criar.error} className="mb-3" />

      <div className="grid gap-4 xl:grid-cols-[320px_1fr]">
        <div className="space-y-3">
          <Card>
            <CardHeader title="O que planejar" />
            <div className="space-y-3 p-4">
              <FormField label="Talhão">
                <select
                  className="input"
                  value={fieldId}
                  onChange={(evento) => {
                    setFieldId(evento.target.value)
                    setPlano(null)
                  }}
                >
                  <option value="">Escolha um talhão</option>
                  {(talhoes.data ?? []).map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name} · {fmt.hectares(item.area_ha)}
                    </option>
                  ))}
                </select>
              </FormField>

              {semContorno && (
                <p className="flex items-start gap-1.5 text-[12px] text-warning">
                  <AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden />
                  Este talhão não tem contorno desenhado. Sem polígono não há área, rota nem
                  cerca virtual — desenhe-o antes.
                </p>
              )}

              <FormField label="Modelo do rover">
                <select
                  className="input"
                  value={modelo}
                  onChange={(evento) => setModelo(evento.target.value)}
                >
                  {(modelos.data ?? []).map((item) => (
                    <option key={item.code} value={item.code}>
                      {item.name}
                    </option>
                  ))}
                </select>
              </FormField>

              <FormField
                label="Direção das linhas (azimute)"
                hint="Graus a partir do norte. O rover anda ao longo das linhas; atravessar passaria por cima das plantas."
              >
                <input
                  className="input num"
                  inputMode="decimal"
                  value={azimute}
                  onChange={(evento) => setAzimute(evento.target.value)}
                />
              </FormField>

              <FormField label="Largura da passada (m)" hint="Vazio usa a do modelo.">
                <input
                  className="input num"
                  inputMode="decimal"
                  value={faixa}
                  onChange={(evento) => setFaixa(evento.target.value)}
                  placeholder="3.0"
                />
              </FormField>

              <FormField label="Bateria na partida (%)">
                <input
                  className="input num"
                  inputMode="decimal"
                  value={bateria}
                  onChange={(evento) => setBateria(evento.target.value)}
                />
              </FormField>

              <FormField
                label="Folga do obstáculo (m)"
                hint="Quanto a rota se afasta da borda de uma mata. O contorno lido por imagem é grosseiro — raspá-lo é entrar nele."
              >
                <input
                  className="input num"
                  inputMode="decimal"
                  value={margem}
                  onChange={(evento) => setMargem(evento.target.value)}
                />
              </FormField>

              <Button
                className="w-full"
                disabled={!fieldId || semContorno || planejar.isPending}
                onClick={calcular}
              >
                <Route className="size-4" aria-hidden />
                {planejar.isPending ? 'Calculando…' : 'Calcular rota'}
              </Button>
            </div>
          </Card>

          {plano && (
            <Card>
              <CardHeader title="Confirmar missão" />
              <div className="space-y-3 p-4">
                <p className="text-[12px] text-ink-2">
                  A missão nasce em rascunho, sem assinatura. Aprovação e checagem de segurança
                  vêm depois, na tela da missão.
                </p>
                <FormField label="Rover">
                  <select
                    className="input"
                    value={deviceId}
                    onChange={(evento) => setDeviceId(evento.target.value)}
                  >
                    <option value="">Escolha o rover</option>
                    {rovers.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.name}
                        {item.battery_percent != null &&
                          ` · ${fmt.number(item.battery_percent)}%`}
                      </option>
                    ))}
                  </select>
                </FormField>
                {rovers.length === 0 && (
                  <p className="text-[12px] text-warning">
                    Nenhum rover cadastrado neste cliente.
                  </p>
                )}
                <Button
                  className="w-full"
                  disabled={!deviceId || criar.isPending}
                  onClick={gerarMissao}
                >
                  <Check className="size-4" aria-hidden />
                  {criar.isPending ? 'Criando…' : 'Gerar missão'}
                </Button>
              </div>
            </Card>
          )}
        </div>

        <div className="space-y-3">
          <Card className="overflow-hidden">
            <FarmMap
              className="h-[min(56vh,520px)]"
              fields={campo ? [campo] : (talhoes.data ?? [])}
              highlightFieldId={fieldId || undefined}
              route={plano?.rota ?? []}
              posts={plano?.postes ?? []}
              obstacles={obstaculos}
            />
            <div className="border-t border-line-soft px-4 py-3">
              <PlanLegend />
            </div>
          </Card>

          {!plano ? (
            <Card>
              <Empty title="Nenhum plano ainda">
                Escolha o talhão e calcule a rota. Nada é gravado enquanto você experimenta.
              </Empty>
            </Card>
          ) : (
            <ResultadoDoPlano plano={plano} />
          )}
        </div>
      </div>
    </>
  )
}

function ResultadoDoPlano({ plano }: { plano: PlanOut }) {
  return (
    <div className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Stat
          label="Distância total"
          value={fmt.meters(plano.metros_totais)}
          hint={`${plano.passadas} passadas de ${fmt.number(plano.swath_m, 1)} m`}
          icon={<Route className="size-4" />}
        />
        <Stat
          label="Tempo estimado"
          value={`${fmt.number(plano.horas_totais, 1)} h`}
          hint={`${fmt.number(plano.minutos_dirigindo)} min dirigindo · ${fmt.number(
            plano.minutos_de_manobra,
          )} min manobrando`}
          icon={<Timer className="size-4" />}
        />
        <Stat
          label="Energia"
          value={`${fmt.number(plano.wh_totais)} Wh`}
          hint={`${plano.cargas} recarga(s) · ${fmt.number(plano.minutos_de_recarga)} min parado`}
          icon={<Zap className="size-4" />}
        />
        <Stat
          label={plano.operable_area_ha == null ? 'Ritmo' : 'Área operável'}
          value={
            plano.operable_area_ha == null
              ? `${fmt.number(plano.ha_por_hora, 2)} ha/h`
              : fmt.hectares(plano.operable_area_ha)
          }
          hint={
            plano.operable_area_ha == null
              ? `${fmt.hectares(plano.area_ha)} · azimute ${fmt.number(plano.azimute_deg)}°`
              : `de ${fmt.hectares(plano.area_ha)} no contorno · ${fmt.number(
                  plano.ha_por_hora,
                  2,
                )} ha/h`
          }
          icon={<Compass className="size-4" />}
        />
      </div>

      {(plano.avoided ?? 0) > 0 && (
        <p className="flex items-start gap-1.5 rounded-[10px] border border-line-soft px-3 py-2 text-[12px] text-ink-2">
          <ShieldCheck className="mt-0.5 size-3.5 shrink-0 text-good" aria-hidden />
          <span>
            <strong>A rota contorna {plano.avoided} obstáculo(s)</strong>, somando{' '}
            {fmt.hectares(plano.area_contornada_ha ?? 0)}. As passadas que os atravessavam
            foram partidas em duas — por isso há mais passadas e menos metros de linha do que
            num talhão limpo do mesmo tamanho.
          </span>
        </p>
      )}

      {!plano.perfil_medido && (
        <p className="flex items-start gap-1.5 rounded-[10px] border border-line-soft px-3 py-2 text-[12px] text-ink-2">
          <AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-warning" aria-hidden />
          <span>
            <strong>Estimativa.</strong> O consumo veio do datasheet do modelo, não de missão
            medida em campo. Depois da primeira missão completa o perfil é recalibrado com o
            que o rover realmente gastou.
          </span>
        </p>
      )}

      {(plano.avisos ?? []).map((aviso) => (
        <p key={aviso} className="flex items-start gap-1.5 text-[12px] text-warning">
          <AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden />
          {aviso}
        </p>
      ))}

      {plano.terrain?.resolution_ok && (plano.terrain.objects ?? []).length > 0 && (
        <Card>
          <CardHeader
            title="O que a imagem achou no caminho"
            actions={
              <Badge tone="neutral">
                {plano.terrain.heuristic ? 'Heurística — confira' : 'Modelo treinado'}
              </Badge>
            }
          />
          <ListaDeObstaculos objetos={plano.terrain.objects ?? []} />
        </Card>
      )}

      <Card>
        <CardHeader
          title="Postes de energia"
          actions={<Badge tone={plano.postes.length ? 'warning' : 'good'}>
            {plano.postes.length ? `${plano.postes.length} necessário(s)` : 'Nenhum necessário'}
          </Badge>}
        />
        {plano.postes.length === 0 ? (
          <Empty title="A bateria cobre o talhão inteiro">
            Nenhum ponto de recarga é preciso para esta rota.
          </Empty>
        ) : (
          <Table>
            <thead>
              <tr>
                <th className={th}>#</th>
                <th className={th}>Posição</th>
                <th className={th}>No percurso</th>
                <th className={th}>Bateria na chegada</th>
                <th className={th}>Recarga</th>
                <th className={th}>Motivo</th>
              </tr>
            </thead>
            <tbody>
              {plano.postes.map((poste) => (
                <tr key={poste.ordem}>
                  <td className={`${td} num`}>{poste.ordem}</td>
                  <td className={`${td} num text-[12px]`}>
                    {poste.lat.toFixed(5)}, {poste.lon.toFixed(5)}
                  </td>
                  <td className={`${td} num`}>{fmt.meters(poste.metros_no_percurso)}</td>
                  <td className={td}>
                    <Badge tone={poste.bateria_na_chegada_percent < 15 ? 'critical' : 'warning'}>
                      {fmt.number(poste.bateria_na_chegada_percent)}%
                    </Badge>
                  </td>
                  <td className={`${td} num`}>{fmt.number(poste.minutos_de_recarga)} min</td>
                  <td className={`${td} text-[12px] text-ink-2`}>{poste.motivo}</td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>
    </div>
  )
}

/** Exportado para a tela do talhão reaproveitar a lista de objetos lidos. */
export function ListaDeObstaculos({ objetos }: { objetos: TerrainObjectOut[] }) {
  if (!objetos.length) return null
  return (
    <Table>
      <thead>
        <tr>
          <th className={th}>O que é</th>
          <th className={th}>Área</th>
          <th className={th}>Rover</th>
          <th className={th}>Confiança</th>
        </tr>
      </thead>
      <tbody>
        {objetos.map((objeto, indice) => (
          <tr key={`${objeto.kind}-${indice}`}>
            <td className={td}>{terrainKind(objeto.kind)}</td>
            <td className={`${td} num`}>{fmt.hectares(objeto.area_ha)}</td>
            <td className={td}>
              <Badge tone={objeto.traversable ? 'warning' : 'critical'}>
                {objeto.traversable ? 'Atravessa' : 'Desvia'}
              </Badge>
            </td>
            <td className={`${td} num`}>{fmt.percent(objeto.confidence)}</td>
          </tr>
        ))}
      </tbody>
    </Table>
  )
}
