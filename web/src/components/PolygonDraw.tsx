import { Eraser, Undo2 } from 'lucide-react'

import type { FieldOut, ZoneOut } from '@/api/types'
import { FarmMap } from '@/components/FarmMap'
import { Button } from '@/components/ui'
import { fmt } from '@/lib/format'
import { areaHa } from '@/lib/geo'

/** Desenho de polígono clicando no mapa: um vértice por clique. */
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
  return (
    <div>
      <FarmMap
        className="h-80"
        fields={fields}
        zones={zones}
        highlightFieldId={highlightFieldId}
        draftPolygon={value}
        onMapClick={(point) => onChange([...value, point])}
      />
      <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-[12px] text-ink-2">
        <span className="num">
          {value.length} vértice(s)
          {value.length >= 3 ? ` · aproximadamente ${fmt.hectares(areaHa(value))}` : ' · clique no mapa para marcar os cantos'}
        </span>
        <span className="flex gap-1">
          <Button size="sm" variant="ghost" icon={<Undo2 className="size-4" />} disabled={!value.length} onClick={() => onChange(value.slice(0, -1))}>
            Desfazer
          </Button>
          <Button size="sm" variant="ghost" icon={<Eraser className="size-4" />} disabled={!value.length} onClick={() => onChange([])}>
            Limpar
          </Button>
        </span>
      </div>
    </div>
  )
}
