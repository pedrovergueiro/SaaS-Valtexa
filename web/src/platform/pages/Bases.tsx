import { Map as MapIcon, RadioTower } from 'lucide-react'
import { useMemo, useState } from 'react'

import { Badge, Card, CardHeader, Empty, ErrorBox, PageHeader, Spinner } from '@/components/ui'
import {
  COR_DA_CLASSE,
  type ClasseDeCelula,
  type MapaCobertura,
  ROTULO_DA_CLASSE,
  area_m2,
  contagem,
  fracoes,
  grade,
} from '@/lib/cobertura'
import { filaDoUplink, resumoDoEnlace, rotuloDoEnlace, tomDoEnlace } from '@/lib/enlace'
import { fmt } from '@/lib/format'
import { type FarmBase, type TalhaoDaBase, useCoberturaDoTalhao, usePlatformBases } from '@/platform/api'

/**
 * Bases da fazenda (console da plataforma): a Starlink de cada base, a fila do uplink, cada
 * Rover que ela atende com cada rádio e as repetidoras. É o retrato que a base manda
 * assinado (VALTEXA-BASE, ``valtexa_base.plataforma``); atualiza a cada 5 s.
 */
export default function Bases() {
  const bases = usePlatformBases()
  return (
    <>
      <PageHeader
        eyebrow="Centro de comando"
        title="Bases da fazenda"
        subtitle="Nuvem → Starlink → base → rádios → Rover. Os alarmes (base sem contato, enlace degradado, fila crescendo, repetidora fraca) saem em Saúde do sistema."
      />
      {bases.isLoading && <Spinner />}
      <ErrorBox error={bases.error} />
      {bases.data && bases.data.length === 0 && (
        <Card>
          <Empty title="Nenhuma base na frota" icon={<RadioTower className="size-5" />}>
            Provisione a base com <code>valtexa-base provisionar</code> (modelo FARM_BASE_V1).
          </Empty>
        </Card>
      )}
      <div className="space-y-5">
        {bases.data?.map((b) => (
          <BaseCard key={b.id} base={b} />
        ))}
      </div>
    </>
  )
}

function BaseCard({ base }: { base: FarmBase }) {
  const fila = filaDoUplink(base.uplink)
  const online = base.internet?.ok
  return (
    <Card>
      <CardHeader
        title={
          <span className="flex items-center gap-2">
            <RadioTower className="size-4" /> {base.name}
            <span className="text-[12px] font-normal text-muted">{base.serial_number}</span>
          </span>
        }
        subtitle={`Contato ${fmt.ago(base.last_seen_at)} · retrato ${base.reportado_em ? fmt.ago(base.reportado_em) : '—'}`}
      />
      <div className="px-5 pb-5">
        <div className="num mb-4 flex flex-wrap gap-2 text-[12px]">
          <Badge tone={online == null ? 'neutral' : online ? 'good' : 'critical'}>
            {online == null ? 'internet sem medida' : online ? 'Starlink no ar' : 'sem internet'}
          </Badge>
          <Badge tone={fila.urgentes > 50 ? 'warning' : 'neutral'}>{fila.urgentes} urgentes na fila</Badge>
          <Badge tone="neutral">{fila.lote} no lote (P4)</Badge>
          {base.custodia != null && <Badge tone="neutral">{base.custodia} em custódia</Badge>}
          {base.disk_percent != null && (
            <Badge tone={base.disk_percent > 90 ? 'warning' : 'neutral'}>disco {fmt.number(base.disk_percent)}%</Badge>
          )}
          {base.internet?.quedas != null && <Badge tone="neutral">{base.internet.quedas} quedas da Starlink</Badge>}
        </div>

        <div className="mb-1 text-[12px] font-medium tracking-wide text-muted uppercase">
          Rovers ({base.rovers_vivos} de {base.rovers.length} no ar)
        </div>
        {base.rovers.length === 0 && <div className="text-[13px] text-muted">Nenhum Rover cadastrado nesta base.</div>}
        <div className="space-y-3">
          {base.rovers.map((r) => (
            <div key={r.serial} className="rounded-lg border border-line p-3">
              <div className="mb-2 flex items-center gap-2 text-[13px]">
                <Badge tone={r.vivo ? 'good' : r.em_travessia ? 'warning' : 'critical'}>{r.serial}</Badge>
                <span className="text-muted">
                  {r.vivo
                    ? `no ar${r.melhor ? ` · lote pelo ${r.melhor}` : ''}`
                    : r.em_travessia
                      ? 'em zona morta mapeada'
                      : 'sem nenhum rádio'}
                </span>
              </div>
              {r.enlaces.map((e) => (
                <div key={e.nome} className="num flex items-center justify-between gap-2 text-[12px]">
                  <span className="flex items-center gap-1.5">
                    <Badge tone={tomDoEnlace(e)}>{e.nome}</Badge> {rotuloDoEnlace(e)}
                  </span>
                  <span className="text-muted">{resumoDoEnlace(e)}</span>
                </div>
              ))}
            </div>
          ))}
        </div>

        {base.repetidoras.length > 0 && (
          <>
            <div className="mt-4 mb-1 text-[12px] font-medium tracking-wide text-muted uppercase">Repetidoras</div>
            <div className="flex flex-wrap gap-2">
              {base.repetidoras.map((x) => (
                <Badge
                  key={x.nome}
                  tone={!x.vivo ? 'critical' : x.bateria_pct != null && x.bateria_pct < 20 ? 'warning' : 'good'}
                >
                  {x.nome} ·{' '}
                  {x.vivo
                    ? x.bateria_pct != null
                      ? `${fmt.number(x.bateria_pct)}% bateria`
                      : 'no ar'
                    : 'sem responder'}
                </Badge>
              ))}
            </div>
          </>
        )}

        {base.talhoes && base.talhoes.length > 0 && <CoberturaDosTalhoes talhoes={base.talhoes} />}
      </div>
    </Card>
  )
}

/**
 * O mapa de cobertura do rádio de cada talhão que a base atende: o que o levantamento
 * mediu (``valtexa-base levantamento --publicar-talhao``). Toda missão nova do talhão leva
 * este mapa assinado — o Rover antecipa a sincronização antes das zonas mortas.
 */
function CoberturaDosTalhoes({ talhoes }: { talhoes: TalhaoDaBase[] }) {
  const medidos = talhoes.filter((t) => t.cobertura_em)
  const [escolhido, setEscolhido] = useState<string | null>(null)
  const atual = escolhido ?? medidos[0]?.id ?? null
  const cobertura = useCoberturaDoTalhao(atual)
  return (
    <>
      <div className="mt-4 mb-1 flex items-center gap-1.5 text-[12px] font-medium tracking-wide text-muted uppercase">
        <MapIcon className="size-3.5" /> Cobertura do rádio por talhão
      </div>
      <div className="mb-3 flex flex-wrap gap-2">
        {talhoes.map((t) => (
          <button
            key={t.id}
            type="button"
            disabled={!t.cobertura_em}
            onClick={() => setEscolhido(t.id)}
            aria-pressed={t.id === atual}
            title={
              t.cobertura_em
                ? `levantamento ${fmt.ago(t.cobertura_em)}`
                : 'sem levantamento: rode valtexa-base levantamento --publicar-talhao'
            }
            className={`rounded-md border px-2 py-1 text-[12px] disabled:cursor-not-allowed disabled:opacity-50 ${
              t.id === atual ? 'border-accent bg-accent-soft' : 'border-line hover:bg-raised'
            }`}
          >
            {t.name}
            <span className="ml-1.5 text-muted">
              {t.cobertura_em
                ? t.zonas_mortas
                  ? `${t.zonas_mortas} zona(s) morta(s)`
                  : 'sem zona morta'
                : 'sem levantamento'}
            </span>
          </button>
        ))}
      </div>
      {medidos.length === 0 && (
        <div className="text-[13px] text-muted">
          Nenhum talhão desta base tem levantamento ainda. Ande o Rover com o registrador ligado e rode{' '}
          <code>valtexa-base levantamento --publicar-talhao &lt;talhão&gt; --config base.json</code>.
        </div>
      )}
      {cobertura.isLoading && atual && <Spinner />}
      <ErrorBox error={cobertura.error} />
      {cobertura.data?.mapa && <MapaDeCobertura mapa={cobertura.data.mapa} medidoEm={cobertura.data.cobertura_em} />}
    </>
  )
}

const CLASSES: ClasseDeCelula[] = ['bom', 'marginal', 'morto']

function MapaDeCobertura({ mapa, medidoEm }: { mapa: MapaCobertura; medidoEm: string | null }) {
  const g = useMemo(() => grade(mapa), [mapa])
  const c = contagem(mapa)
  const f = fracoes(mapa)
  if (g.celulas.length === 0) return <div className="text-[13px] text-muted">Levantamento sem células medidas.</div>
  // um traço de escala redondo (10, 20, 50, 100… m) com ~1/4 da largura
  const alvo = g.largura_m / 4
  const escala = [10, 20, 50, 100, 200, 500, 1000].reduce((a, b) => (Math.abs(b - alvo) < Math.abs(a - alvo) ? b : a))
  const escalaCel = escala / mapa.celula_m
  const marca = Math.max(0.6, g.colunas / 50)
  return (
    <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_minmax(0,280px)]">
      <figure className="min-w-0">
        <svg
          viewBox={`-0.5 -0.5 ${g.colunas + 1} ${g.linhas + 2}`}
          className="max-h-[420px] w-full rounded-lg border border-line bg-raised"
          role="img"
          aria-label={`Mapa de cobertura: ${c.bom} células boas, ${c.marginal} marginais, ${c.morto} mortas`}
        >
          {g.celulas.map((cel) => (
            <rect
              key={`${cel.i},${cel.j}`}
              x={cel.x}
              y={cel.y}
              width={1}
              height={1}
              fill={COR_DA_CLASSE[cel.classe]}
              fillOpacity={cel.classe === 'bom' ? 0.45 : 0.75}
            >
              <title>{`célula ${cel.i},${cel.j}: ${ROTULO_DA_CLASSE[cel.classe]}`}</title>
            </rect>
          ))}
          {mapa.zonas_mortas.map((z) => {
            const pos = z.celulas.map(([i, j]) => g.posicao(i, j)).filter((p) => p != null)
            if (pos.length === 0) return null
            const x = pos.reduce((s, p) => s + p.x, 0) / pos.length + 0.5
            const y = pos.reduce((s, p) => s + p.y, 0) / pos.length + 0.5
            return (
              <text
                key={z.id}
                x={x}
                y={y}
                textAnchor="middle"
                dominantBaseline="central"
                fontSize={marca * 1.2}
                className="fill-current font-semibold"
              >
                Z{z.id}
              </text>
            )
          })}
          {mapa.repetidoras.map((r, k) => {
            const p = r.celula ? g.posicao(r.celula[0], r.celula[1]) : null
            if (!p) return null
            return (
              <g key={k}>
                <circle
                  cx={p.x + 0.5}
                  cy={p.y + 0.5}
                  r={marca}
                  className="fill-accent stroke-white"
                  strokeWidth={marca / 4}
                />
                <text
                  x={p.x + 0.5}
                  y={p.y + 0.5}
                  textAnchor="middle"
                  dominantBaseline="central"
                  fontSize={marca * 1.1}
                  className="fill-white font-bold"
                >
                  {r.ordem ?? k + 1}
                </text>
                <title>{r.explicacao ?? 'repetidora sugerida'}</title>
              </g>
            )
          })}
          <g transform={`translate(0 ${g.linhas + 0.6})`}>
            <line x1={0} x2={escalaCel} y1={0} y2={0} className="stroke-current" strokeWidth={0.15} />
            <text x={escalaCel + 0.4} y={0} dominantBaseline="central" fontSize={marca * 1.2} className="fill-current">
              {escala} m · N ↑
            </text>
          </g>
        </svg>
        <figcaption className="mt-1 text-[12px] text-muted">
          Medido {medidoEm ? fmt.ago(medidoEm) : '—'} · célula de {fmt.number(mapa.celula_m)} m ·{' '}
          {fmt.number(g.largura_m)} × {fmt.number(g.altura_m)} m
          {mapa.amostras != null && ` · ${fmt.number(mapa.amostras)} amostras`}
        </figcaption>
      </figure>
      <div className="space-y-3 text-[13px]">
        <div className="space-y-1.5">
          {CLASSES.map((k) => (
            <div key={k} className="num flex items-center justify-between gap-2">
              <span className="flex items-center gap-2">
                <span className="inline-block size-3 rounded-sm" style={{ background: COR_DA_CLASSE[k] }} />
                {ROTULO_DA_CLASSE[k]}
              </span>
              <span className="text-muted">
                {Math.round(f[k] * 100)}% · {fmt.number(area_m2(mapa, c[k]))} m²
              </span>
            </div>
          ))}
        </div>
        {mapa.zonas_mortas.length > 0 && (
          <div>
            <div className="mb-1 text-[12px] font-medium text-muted uppercase">Zonas mortas</div>
            {mapa.zonas_mortas.map((z) => (
              <div key={z.id} className="num flex justify-between text-[12px]">
                <span>Z{z.id}</span>
                <span className="text-muted">{fmt.number(z.area_m2)} m² · o Rover atravessa sem pausar</span>
              </div>
            ))}
          </div>
        )}
        {mapa.repetidoras.length > 0 && (
          <div>
            <div className="mb-1 text-[12px] font-medium text-muted uppercase">Repetidoras sugeridas</div>
            {mapa.repetidoras.map((r, k) => (
              <div key={k} className="mb-1 text-[12px]">
                <Badge tone="neutral">{r.ordem ?? k + 1}</Badge>{' '}
                {r.ganho_fracao != null ? `cobre ${Math.round(r.ganho_fracao * 100)}% do tempo sem rádio` : 'sugerida'}
                {r.confianca && <span className="text-muted"> · confiança {r.confianca}</span>}
              </div>
            ))}
            {mapa.fracao_morta_coberta != null && (
              <div className="text-[12px] text-muted">
                Com todas: {Math.round(mapa.fracao_morta_coberta * 100)}% do tempo morto passa a ter rádio.
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
