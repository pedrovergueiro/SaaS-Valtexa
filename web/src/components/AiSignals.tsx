/**
 * O que a IA disse além do rótulo.
 *
 * Três coisas que mudam o que o agrônomo faz com o item: o portão de
 * enquadramento (a foto é folha?), o conjunto conformal (entre quais classes a
 * IA não sabe escolher) e, num quadro do rover, os recortes por zona da planta
 * e a severidade da Sigatoka.
 */
import type { AiSignals, DetectionOut, FrameSignals } from '@/api/types'
import { Badge, Meter } from '@/components/ui'
import { fmt } from '@/lib/format'
import { disease, plantZone, scene } from '@/lib/labels'

/** Os sinais da análise primária — a única que chama o portão e o quadro. */
export function primarySignals(detections: DetectionOut[] | undefined): AiSignals | null {
  const found = (detections ?? []).find(
    (item) => item.source !== 'human' && item.signals && Object.keys(item.signals).length > 0,
  )
  return found ? (found.signals as AiSignals) : null
}

export function AiSignalsPanel({ signals }: { signals: AiSignals }) {
  const set = signals.prediction_set
  return (
    <div className="flex flex-col gap-3 text-[13px]">
      {signals.in_scope === false && (
        <div className="rounded-[10px] border border-warning/40 bg-warning/10 p-3">
          <div className="font-medium">Não é folha: {scene(signals.scene)}</div>
          <p className="mt-1 text-[12px] text-ink-2">
            O portão de enquadramento recusou antes do diagnóstico. Nomear o que é — pseudocaule, tronco, fruto — alimenta
            o próximo modelo.
          </p>
        </div>
      )}
      {set && (
        <div>
          <div className="mb-1 font-medium">Conjunto conformal</div>
          {set.length === 0 ? (
            <p className="text-[12px] text-ink-2">Vazio: nenhuma classe do treino é plausível para esta imagem.</p>
          ) : (
            <>
              <div className="flex flex-wrap gap-1.5">
                {set.map((label) => (
                  <Badge key={label} tone={set.length > 1 ? 'warning' : 'info'}>
                    {disease(label)}
                  </Badge>
                ))}
              </div>
              {set.length > 1 && (
                <p className="mt-1 text-[12px] text-ink-2">A IA não consegue separar estas classes nesta imagem.</p>
              )}
            </>
          )}
        </div>
      )}
      {signals.frame && <FramePanel frame={signals.frame} />}
    </div>
  )
}

function FramePanel({ frame }: { frame: FrameSignals }) {
  const zones = Object.entries(frame.zone_summary ?? {})
  const shares = Object.entries(frame.class_share ?? {}).sort((a, b) => b[1] - a[1]).slice(0, 4)
  const sigatoka = frame.sigatoka
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <span className="font-medium">Quadro do rover</span>
        <span className="num text-[12px] text-ink-2">
          {frame.tiles_in_scope} de {frame.tiles_analyzed} recortes são folha
        </span>
      </div>

      {zones.length > 0 && (
        <ul className="grid gap-1.5 sm:grid-cols-2">
          {zones.map(([zone, count]) => (
            <li key={zone} className="rounded-[10px] bg-sunken px-3 py-2 text-[12px]">
              <div className="font-medium text-ink">{plantZone(zone)}</div>
              <div className="num text-ink-2">
                {count.recortes} recortes · {count.com_achado} com achado
                {count.fora_de_escopo ? ` · ${count.fora_de_escopo} fora do escopo` : ''}
              </div>
            </li>
          ))}
        </ul>
      )}

      {shares.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <div className="text-[12px] text-muted">Fração dos recortes por classe — não é probabilidade do modelo</div>
          {shares.map(([label, share]) => (
            <div key={label} className="grid grid-cols-[8rem_1fr_3rem] items-center gap-2 text-[12px]">
              <span className="truncate">{disease(label)}</span>
              <Meter value={share} tone={label === 'Healthy' ? 'good' : 'warning'} label={disease(label)} />
              <span className="num text-right text-ink-2">{fmt.percent(share)}</span>
            </div>
          ))}
        </div>
      )}

      {frame.needs_review_share > 0 && (
        <p className="text-[12px] text-ink-2">
          <span className="num">{fmt.percent(frame.needs_review_share)}</span> dos recortes destoam do que o modelo
          conhece.
        </p>
      )}

      {sigatoka && sigatoka.dsi != null && (
        <div className="rounded-[10px] border border-line-soft p-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="font-medium">Severidade da Sigatoka (DSI)</span>
            <span className="num">
              <strong>{fmt.number(sigatoka.dsi, 1)}%</strong>
              {sigatoka.dsi_ci_low != null && sigatoka.dsi_ci_high != null && (
                <span className="text-muted">
                  {' '}
                  ({fmt.number(sigatoka.dsi_ci_low, 1)}–{fmt.number(sigatoka.dsi_ci_high, 1)})
                </span>
              )}
            </span>
          </div>
          <p className="mt-1 text-[12px] text-ink-2">
            Escala de Stover-Gauhl sobre {sigatoka.n_crops_used} recortes das folhas baixas. É o que uma câmera vê, não a
            planta inteira.
          </p>
          {!sigatoka.scale_validated && (
            <Badge tone="warning" className="mt-2">
              Escala ainda não validada por agrônomo
            </Badge>
          )}
        </div>
      )}
    </div>
  )
}
