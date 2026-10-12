import { AlertTriangle, Check, Eraser, MapPin, Route, Sparkles, Undo2, Zap } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'

import { usePlanField, useField, useFields, useRefineBoundary, useUpdateFieldBoundary, useZones } from '@/api/queries'
import { ApiError } from '@/api/client'
import type { BoundaryRefineOut, PlanOut } from '@/api/types'
import { BuscaDeLugar } from '@/components/BuscaDeLugar'
import { FarmMap, PlanLegend } from '@/components/FarmMap'
import { Badge, Button, Card, ErrorBox, PageHeader, Spinner, Table, td, th } from '@/components/ui'
import { fmt } from '@/lib/format'
import { areaHa, parseCoords } from '@/lib/geo'
import { coverClass, terrainKind } from '@/lib/labels'
import { enquadramento } from '@/lib/localizar'

/**
 * Editor do contorno do talhão, em tela cheia — do endereço do cliente à rota do rover.
 *
 * 1. **Achar a lavoura:** endereço, cidade, nome da fazenda, coordenada ou link do
 *    Google Maps. O mapa vai direto para lá.
 * 2. **Desenhar** por cima, com poucos cliques, sem precisão.
 * 3. **Ajustar com IA e calcular a rota**, num botão: o encaixe acha a borda que existe
 *    na imagem (café × mata × carreador), lê as ruas e os obstáculos, e o planejador
 *    devolve as passadas no sentido das ruas, desviando dos bloqueios, com o tempo, a
 *    energia e os postes de recarga. Sem imagem para a IA, a rota sai do desenho e a
 *    tela diz por quê.
 * 4. **Conferir e salvar.** O encaixe é sugestão, nunca decisão: nada é gravado sem
 *    alguém apertar salvar.
 */
export default function BoundaryEditor() {
  const { id = '' } = useParams()
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const campo = useField(id)
  const todos = useFields()
  const zonas = useZones(id)
  const encaixar = useRefineBoundary()
  const planejar = usePlanField(id)
  const salvar = useUpdateFieldBoundary(id)

  const [contorno, setContorno] = useState<number[][] | null>(null)
  const [texto, setTexto] = useState('')
  const [foco, setFoco] = useState<[number, number] | undefined>()
  const [focoZoom, setFocoZoom] = useState(17)
  const [caixa, setCaixa] = useState<[[number, number], [number, number]] | undefined>()
  const [recado, setRecado] = useState<string | null>(null)
  const [resultado, setResultado] = useState<BoundaryRefineOut | null>(null)
  const [plano, setPlano] = useState<PlanOut | null>(null)
  const [semIa, setSemIa] = useState<string | null>(null)
  const [tolerancia, setTolerancia] = useState(35)
  const [azimute, setAzimute] = useState<string>('')

  const atual = contorno ?? campo.data?.boundary ?? []
  const area = useMemo(() => (atual.length >= 3 ? areaHa(atual) : 0), [atual])
  const original = campo.data?.boundary ?? []
  const mudou = contorno !== null
  const azimuteDoTalhao = campo.data?.row_azimuth_deg ?? null

  function semEnquadramento() {
    setFoco(undefined)
    setCaixa(undefined)
  }

  function aplicarCoordenadas() {
    const { points, aviso } = parseCoords(texto)
    if (!points.length) {
      setRecado(aviso ?? 'Cole ao menos uma coordenada.')
      return
    }
    if (points.length === 1) {
      const [lon = 0, lat = 0] = points[0]!
      setCaixa(undefined)
      setFoco([lat, lon])
      setRecado(`Mapa centrado em ${lat.toFixed(5)}, ${lon.toFixed(5)}.`)
      return
    }
    usarContorno(points)
    setRecado(`${points.length} vértices · ${fmt.hectares(areaHa(points))}. ${aviso ?? ''}`.trim())
  }

  function usarContorno(points: number[][]) {
    setContorno(points)
    setResultado(null)
    setPlano(null)
    const [lon = 0, lat = 0] = points[0]!
    setCaixa(undefined)
    setFoco([lat, lon])
  }

  /** A rota do contorno (encaixado ou desenhado), no sentido das ruas quando a IA as leu. */
  async function calcularRota(anel: number[][], leitura: BoundaryRefineOut | null) {
    const lido = leitura?.rows?.detected ? leitura.rows.azimuth_deg : null
    const escolhido = azimute.trim() ? Number(azimute.replace(',', '.')) : null
    const direcao = escolhido ?? lido ?? azimuteDoTalhao ?? 90
    if (escolhido == null && lido != null) setAzimute(String(Math.round(lido)))
    try {
      const novo = await planejar.mutateAsync({
        device_model_code: 'ROVER_V3',
        start_battery_percent: 100,
        obstacle_margin_m: 2,
        boundary: anel,
        terrain: leitura?.terrain ?? undefined,
        row_azimuth_deg: ((direcao % 360) + 360) % 360,
      })
      setPlano(novo)
    } catch {
      setPlano(null) /* o erro aparece no ErrorBox */
    }
  }

  async function ajustarECalcular() {
    setRecado(null)
    setSemIa(null)
    setPlano(null)
    try {
      const resposta = await encaixar.mutateAsync({ polygon: atual, tolerance: tolerancia / 100, vertices: 48 })
      setContorno(resposta.polygon)
      setResultado(resposta)
      semEnquadramento()
      await calcularRota(resposta.polygon, resposta)
    } catch (erro) {
      // Sem imagem para a IA (ou o serviço fora do ar): a rota sai do desenho mesmo.
      setResultado(null)
      setSemIa(erro instanceof ApiError ? erro.message : String(erro))
      encaixar.reset()
      await calcularRota(atual, null)
    }
  }

  // Vindo do "Novo talhão" com ?ajustar=1: já ajusta e calcula ao abrir.
  const automatico = useRef(false)
  useEffect(() => {
    if (automatico.current || params.get('ajustar') !== '1' || !campo.data?.boundary?.length) return
    automatico.current = true
    void ajustarECalcular()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [campo.data?.boundary, params])

  if (campo.isLoading) return <Spinner label="Abrindo o talhão" />
  if (!campo.data) return <ErrorBox error={campo.error ?? 'Talhão não encontrado.'} />

  const pendente = encaixar.isPending || planejar.isPending
  const planoProibido = planejar.error instanceof ApiError && planejar.error.status === 403

  return (
    <>
      <PageHeader
        title={`Contorno · ${campo.data.name}`}
        subtitle="Ache a lavoura, contorne por cima sem precisão, e a IA encaixa no limite real, lê os obstáculos e calcula a rota — você confere antes de salvar."
        actions={
          <div className="flex items-center gap-2">
            <Badge tone={area ? 'info' : 'neutral'}>{fmt.hectares(area)}</Badge>
            <Button
              variant="ghost"
              disabled={!mudou}
              onClick={() => {
                setContorno(null)
                setResultado(null)
                setPlano(null)
              }}
            >
              Descartar
            </Button>
            <Button
              disabled={!mudou || atual.length < 3 || salvar.isPending}
              onClick={async () => {
                await salvar.mutateAsync({ boundary: atual, terrain: resultado?.terrain })
                navigate(`/talhoes/${id}`)
              }}
            >
              <Check className="size-4" aria-hidden />
              Salvar contorno
            </Button>
          </div>
        }
      />

      <Card className="mb-3">
        <div className="p-4">
          <p className="mb-2 flex items-center gap-2 text-[13px] font-medium">
            <MapPin className="size-4" aria-hidden /> Onde fica a lavoura?
          </p>
          <BuscaDeLugar
            onLugar={(lugar) => {
              const alvo = enquadramento(lugar)
              if ('caixa' in alvo) {
                setFoco(undefined)
                setCaixa(alvo.caixa)
              } else {
                setCaixa(undefined)
                setFocoZoom(alvo.zoom)
                setFoco(alvo.ponto)
              }
            }}
            onContorno={usarContorno}
          />
        </div>
      </Card>

      <ErrorBox error={encaixar.error ?? (planoProibido ? null : planejar.error) ?? salvar.error} className="mb-3" />

      <div className="grid gap-4 xl:grid-cols-[1fr_340px]">
        <Card className="overflow-hidden">
          <FarmMap
            className="h-[calc(100dvh-20rem)] min-h-[440px]"
            fields={todos.data?.filter((item) => item.id !== id)}
            zones={zonas.data}
            draftPolygon={atual}
            obstacles={resultado?.terrain?.objects ?? []}
            route={plano?.rota ?? []}
            posts={plano?.postes ?? []}
            focus={foco}
            focusZoom={focoZoom}
            focusBounds={caixa}
            onMapClick={(ponto) => {
              semEnquadramento()
              setResultado(null)
              setPlano(null)
              setContorno([...(contorno ?? original), ponto])
            }}
          />
          {(resultado?.terrain?.objects?.length || plano) && (
            <div className="border-t border-line-soft px-4 py-3">
              <PlanLegend />
            </div>
          )}
        </Card>

        <div className="space-y-3">
          <Card>
            <div className="space-y-3 p-4">
              <p className="text-[13px] font-medium">Ajustar com IA e calcular a rota</p>
              <p className="text-[12px] text-ink-2">
                Contorne a lavoura com poucos cliques. A IA acha a borda entre o café e a mata, lê as ruas e os
                obstáculos; a rota sai no sentido das ruas, desviando do que bloqueia.
              </p>
              <label className="block text-[12px] text-ink-2">
                Cada lado pode andar até{' '}
                <span className="num">~{Math.round(Math.min(60, 8 + 0.6 * tolerancia))} m</span> para achar o carreador
                <input
                  type="range"
                  min={5}
                  max={60}
                  step={5}
                  value={tolerancia}
                  onChange={(evento) => setTolerancia(Number(evento.target.value))}
                  className="mt-1 w-full"
                />
              </label>
              <Button
                className="w-full"
                variant="primary"
                disabled={atual.length < 3 || pendente}
                onClick={ajustarECalcular}
              >
                <Sparkles className="size-4" aria-hidden />
                {encaixar.isPending
                  ? 'Encaixando…'
                  : planejar.isPending
                    ? 'Calculando a rota…'
                    : 'Ajustar com IA e calcular rota'}
              </Button>
              {atual.length < 3 && <p className="text-[12px] text-muted">Marque ao menos 3 pontos no mapa.</p>}

              {semIa && (
                <p className="flex items-start gap-1.5 text-[12px] text-warning">
                  <AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden />
                  <span>
                    A IA não ajustou desta vez — {semIa}. A rota abaixo saiu do seu desenho, sem desvio de obstáculo.
                  </span>
                </p>
              )}

              {resultado && (
                <div className="space-y-2 border-t border-line-soft pt-3 text-[12px]">
                  {resultado.method === 'carreador' ? (
                    <p>
                      Encaixe nos carreadores: <strong>{(resultado.confidence * 100).toFixed(0)}%</strong> dos lados
                      encostaram na estrada ou na borda · área {resultado.area_change >= 0 ? '+' : ''}
                      {(resultado.area_change * 100).toFixed(0)}%
                    </p>
                  ) : (
                    <p>
                      Borda nítida em <strong>{(resultado.confidence * 100).toFixed(0)}%</strong> das direções · área{' '}
                      {resultado.area_change >= 0 ? '+' : ''}
                      {(resultado.area_change * 100).toFixed(0)}%
                    </p>
                  )}
                  <p className="text-ink-2">Imagem a {resultado.meters_per_pixel} m por pixel.</p>
                  {resultado.rows && (
                    <p className={resultado.rows.detected ? 'text-good' : 'text-ink-2'}>{resultado.rows.description}</p>
                  )}
                  {(resultado.notes ?? []).map((nota) =>
                    nota.startsWith('Encaixou') ? (
                      <p key={nota} className="flex items-start gap-1.5 text-good">
                        <Check className="mt-0.5 size-3.5 shrink-0" aria-hidden />
                        {nota}
                      </p>
                    ) : (
                      <p key={nota} className="flex items-start gap-1.5 text-warning">
                        <AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden />
                        {nota}
                      </p>
                    ),
                  )}
                </div>
              )}
            </div>
          </Card>

          {plano && (
            <PainelDaRota
              plano={plano}
              azimute={azimute}
              setAzimute={setAzimute}
              pendente={planejar.isPending}
              recalcular={() => calcularRota(atual, resultado)}
            />
          )}
          {planoProibido && (
            <Card>
              <p className="p-4 text-[12px] text-ink-2">
                A rota e os postes são calculados pela equipe ValTexa. O contorno que você salvar já vai para ela.
              </p>
            </Card>
          )}

          {resultado?.terrain && <PainelDoTerreno terreno={resultado.terrain} />}

          <Card>
            <div className="space-y-2 p-4">
              <p className="flex items-center gap-2 text-[13px] font-medium">
                <MapPin className="size-4" aria-hidden />
                Colar o contorno
              </p>
              <p className="text-[12px] text-ink-2">
                Uma linha por ponto, do GPS, do Google Maps ou de um KML. Três ou mais desenham o talhão.
              </p>
              <textarea
                className="input min-h-24 font-mono text-[12px]"
                value={texto}
                onChange={(evento) => setTexto(evento.target.value)}
                placeholder={'-21.90400, -45.86200\n-21.90133, -45.86160\n-21.90308, -45.85918'}
              />
              <Button size="sm" variant="secondary" className="w-full" onClick={aplicarCoordenadas}>
                Usar coordenadas
              </Button>
              {recado && <p className="text-[12px] text-ink-2">{recado}</p>}
            </div>
          </Card>

          <Card>
            <div className="flex items-center justify-between gap-2 p-4 text-[12px]">
              <span className="num">{atual.length} vértice(s)</span>
              <span className="flex gap-1">
                <Button
                  size="sm"
                  variant="ghost"
                  icon={<Undo2 className="size-4" />}
                  disabled={!atual.length}
                  onClick={() => {
                    setResultado(null)
                    setPlano(null)
                    setContorno(atual.slice(0, -1))
                  }}
                >
                  Desfazer
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  icon={<Eraser className="size-4" />}
                  disabled={!atual.length}
                  onClick={() => {
                    setResultado(null)
                    setPlano(null)
                    setContorno([])
                  }}
                >
                  Limpar
                </Button>
              </span>
            </div>
          </Card>
        </div>
      </div>
    </>
  )
}

/** A rota do contorno atual: o que o rover faz, quanto tempo leva e onde recarrega. */
function PainelDaRota({
  plano,
  azimute,
  setAzimute,
  pendente,
  recalcular,
}: {
  plano: PlanOut
  azimute: string
  setAzimute: (valor: string) => void
  pendente: boolean
  recalcular: () => void
}) {
  return (
    <Card>
      <div className="space-y-3 p-4">
        <div className="flex items-center justify-between gap-2">
          <p className="flex items-center gap-2 text-[13px] font-medium">
            <Route className="size-4" aria-hidden /> Rota do rover
          </p>
          <Badge tone="info">{plano.device_model_code}</Badge>
        </div>
        <div className="num grid grid-cols-2 gap-2 text-[12px]">
          <Numero rotulo="Área" valor={fmt.hectares(plano.area_ha)} />
          <Numero
            rotulo="Operável"
            valor={plano.operable_area_ha != null ? fmt.hectares(plano.operable_area_ha) : '—'}
          />
          <Numero rotulo="Passadas" valor={String(plano.passadas)} />
          <Numero rotulo="Percurso" valor={`${fmt.number(plano.metros_totais / 1000)} km`} />
          <Numero rotulo="Tempo" valor={`${fmt.number(plano.horas_totais)} h`} />
          <Numero rotulo="Cargas" valor={String(plano.cargas)} />
        </div>
        {plano.postes.length > 0 && (
          <p className="flex items-center gap-1.5 text-[12px]">
            <Zap className="size-3.5 text-warning" aria-hidden />
            {plano.postes.length} poste(s) de recarga no percurso
          </p>
        )}
        {plano.avoided > 0 && (
          <p className="text-[12px] text-ink-2">
            Desvia de {plano.avoided} bloqueio(s) ({fmt.hectares(plano.area_contornada_ha ?? 0)} fora da rota).
          </p>
        )}
        <div className="flex items-end gap-2">
          <label className="flex-1 text-[12px] text-ink-2">
            Direção das ruas (°)
            <input
              className="input num mt-1"
              type="number"
              min={0}
              max={179}
              value={azimute}
              placeholder={String(Math.round(plano.azimute_deg))}
              onChange={(evento) => setAzimute(evento.target.value)}
            />
          </label>
          <Button size="sm" disabled={pendente} onClick={recalcular}>
            Recalcular
          </Button>
        </div>
        {plano.avisos.length > 0 && (
          <ul className="space-y-1 text-[12px] text-warning">
            {plano.avisos.map((aviso) => (
              <li key={aviso} className="flex items-start gap-1.5">
                <AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden />
                {aviso}
              </li>
            ))}
          </ul>
        )}
      </div>
    </Card>
  )
}

function Numero({ rotulo, valor }: { rotulo: string; valor: string }) {
  return (
    <div className="rounded-lg border border-line-soft px-2.5 py-1.5">
      <div className="text-[11px] text-muted">{rotulo}</div>
      <div className="text-[14px] font-semibold">{valor}</div>
    </div>
  )
}

/**
 * O que a leitura de imagem achou dentro do contorno.
 *
 * Mostra a área operável em primeiro lugar porque é o número que muda decisão:
 * é ele, e não a área bruta, que o planejamento de missão deveria usar.
 *
 * Tudo aqui é palpite de cor e textura, e a tela diz isso em vez de esconder.
 * Um obstáculo marcado errado que ninguém questiona vira desvio de rota
 * permanente; um que a pessoa confere vira correção — e é a correção do
 * agrônomo que forma o dataset de um segmentador treinado.
 */
function PainelDoTerreno({ terreno }: { terreno: NonNullable<BoundaryRefineOut['terrain']> }) {
  if (!terreno.resolution_ok) {
    return (
      <Card>
        <div className="space-y-2 p-4">
          <p className="text-[13px] font-medium">Terreno</p>
          <p className="flex items-start gap-1.5 text-[12px] text-warning">
            <AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden />
            {terreno.description}
          </p>
          <p className="text-[12px] text-ink-2">
            O contorno acima continua valendo. O que exige mais resolução é ler obstáculo e
            descontar área.
          </p>
        </div>
      </Card>
    )
  }

  const objetos = terreno.objects ?? []
  const bloqueios = objetos.filter((objeto) => !objeto.traversable)

  return (
    <Card>
      <div className="space-y-3 p-4">
        <div className="flex items-center justify-between gap-2">
          <p className="text-[13px] font-medium">Terreno</p>
          <Badge tone={bloqueios.length ? 'warning' : 'good'}>
            {bloqueios.length ? `${bloqueios.length} bloqueio(s)` : 'Sem bloqueio'}
          </Badge>
        </div>

        {terreno.operable_area_ha != null && (
          <div>
            <p className="font-display text-[22px] leading-none font-semibold">
              {fmt.hectares(terreno.operable_area_ha)}
            </p>
            <p className="text-[12px] text-ink-2">
              operáveis — lavoura mais carreador. É este o número que o planejamento usa, não
              a área bruta.
            </p>
          </div>
        )}

        <ul className="space-y-1 text-[12px] text-ink-2">
          {Object.entries(terreno.cover_fractions ?? {})
            .filter(([, fracao]) => fracao > 0)
            .sort((a, b) => b[1] - a[1])
            .map(([classe, fracao]) => (
              <li key={classe} className="flex justify-between gap-2">
                <span>{coverClass(classe)}</span>
                <span className="num">{fmt.percent(fracao)}</span>
              </li>
            ))}
        </ul>

        {objetos.length > 0 && (
          <Table>
            <thead>
              <tr>
                <th className={th}>Objeto</th>
                <th className={th}>Área</th>
                <th className={th}>Rover</th>
              </tr>
            </thead>
            <tbody>
              {objetos.slice(0, 8).map((objeto, indice) => (
                <tr key={`${objeto.kind}-${indice}`}>
                  <td className={td}>{terrainKind(objeto.kind)}</td>
                  <td className={`${td} num`}>{fmt.hectares(objeto.area_ha)}</td>
                  <td className={td}>
                    <Badge tone={objeto.traversable ? 'warning' : 'critical'}>
                      {objeto.traversable ? 'Atravessa' : 'Desvia'}
                    </Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}

        <p className="text-[12px] text-muted">
          Classificação por cor e textura, não por modelo treinado. Confira antes de salvar — o
          que você corrigir é o que vai formar o dataset.
        </p>
      </div>
    </Card>
  )
}
