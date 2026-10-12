import { Crosshair, Eraser, MapPin, Undo2 } from 'lucide-react'
import { useState } from 'react'

import type { FieldOut, ZoneOut } from '@/api/types'
import { BuscaDeLugar } from '@/components/BuscaDeLugar'
import { FarmMap } from '@/components/FarmMap'
import { Button } from '@/components/ui'
import { fmt } from '@/lib/format'
import { areaHa, parseCoords } from '@/lib/geo'
import { enquadramento } from '@/lib/localizar'

/**
 * Desenho do talhão sobre a imagem de satélite real.
 *
 * Dois caminhos, porque na prática as duas coisas acontecem:
 *
 * **Clicando** — um vértice por clique, quando a pessoa reconhece a lavoura na
 * imagem e contorna o que vê.
 *
 * **Colando coordenadas** — quando ela já tem os pontos: do Google Maps, de um
 * GPS de mão, de um KML do agrimensor. Um ponto só leva o mapa até o lugar
 * (achar a fazenda arrastando o mapa é o que ninguém tem paciência de fazer);
 * três ou mais viram o contorno inteiro de uma vez.
 *
 * A área aparece o tempo todo, e é a conferência que importa: quem sabe que o
 * talhão tem 24 ha percebe na hora se o desenho saiu em 8 ou em 60.
 */
export function PolygonDraw({
  value,
  onChange,
  fields,
  zones,
  highlightFieldId,
}: {
  value: number[][]
  onChange: (next: number[][]) => void
  fields?: FieldOut[]
  zones?: ZoneOut[]
  highlightFieldId?: string
}) {
  const [texto, setTexto] = useState('')
  const [foco, setFoco] = useState<[number, number] | undefined>()
  const [focoZoom, setFocoZoom] = useState(17)
  const [caixa, setCaixa] = useState<[[number, number], [number, number]] | undefined>()
  const [recado, setRecado] = useState<string | null>(null)

  function aplicar() {
    setCaixa(undefined)
    const { points, aviso } = parseCoords(texto)
    if (!points.length) {
      setRecado(aviso ?? 'Cole ao menos uma coordenada.')
      return
    }
    if (points.length === 1) {
      const [lon = 0, lat = 0] = points[0]!
      setFoco([lat, lon])
      setRecado(`Mapa centrado em ${lat.toFixed(5)}, ${lon.toFixed(5)}. ${aviso ?? ''}`.trim())
      return
    }
    onChange(points)
    const [lon = 0, lat = 0] = points[0]!
    setFoco([lat, lon])
    setRecado(
      `${points.length} vértices · ${fmt.hectares(areaHa(points))}. ${aviso ?? ''}`.trim(),
    )
  }

  return (
    <div>
      <BuscaDeLugar
        className="mb-2"
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
        onContorno={(pontos) => {
          onChange(pontos)
          const [lon = 0, lat = 0] = pontos[0]!
          setCaixa(undefined)
          setFoco([lat, lon])
        }}
      />
      <FarmMap
        className="h-80"
        fields={fields}
        zones={zones}
        highlightFieldId={highlightFieldId}
        draftPolygon={value}
        focus={foco}
        focusZoom={focoZoom}
        focusBounds={caixa}
        onMapClick={(point) => {
          setFoco(undefined)
          setCaixa(undefined)
          onChange([...value, point])
        }}
      />

      <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-[12px] text-ink-2">
        <span className="num">
          {value.length} vértice(s)
          {value.length >= 3
            ? ` · aproximadamente ${fmt.hectares(areaHa(value))}`
            : ' · clique no mapa para marcar os cantos'}
        </span>
        <span className="flex gap-1">
          <Button
            size="sm"
            variant="ghost"
            icon={<Undo2 className="size-4" />}
            disabled={!value.length}
            onClick={() => onChange(value.slice(0, -1))}
          >
            Desfazer
          </Button>
          <Button
            size="sm"
            variant="ghost"
            icon={<Eraser className="size-4" />}
            disabled={!value.length}
            onClick={() => onChange([])}
          >
            Limpar
          </Button>
        </span>
      </div>

      <div className="mt-3 rounded-lg border border-line p-3">
        <label className="flex items-center gap-2 text-[12px] font-medium">
          <MapPin className="size-4" aria-hidden />
          Coordenadas do terreno
        </label>
        <p className="mt-1 text-[12px] text-ink-2">
          Cole do Google Maps, do GPS ou de um KML. Uma linha por ponto. Um ponto só leva o mapa
          até a fazenda; três ou mais desenham o talhão.
        </p>
        <textarea
          className="input mt-2 min-h-20 font-mono text-[12px]"
          value={texto}
          onChange={(evento) => setTexto(evento.target.value)}
          placeholder={'-21.90400, -45.86200\n-21.90133, -45.86160\n-21.90308, -45.85918'}
        />
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <Button size="sm" icon={<Crosshair className="size-4" />} onClick={aplicar}>
            Usar coordenadas
          </Button>
          {recado && <span className="text-[12px] text-ink-2">{recado}</span>}
        </div>
      </div>
    </div>
  )
}
