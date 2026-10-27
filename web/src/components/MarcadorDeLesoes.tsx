import { ImageOff, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

import { apiBlob } from '@/api/client'
import { caixaDoArraste, MAX_LESOES, pontoNormalizado, type Caixa } from '@/lib/ensino'

/**
 * A foto inteira (sem recorte, para a caixa bater com a imagem) e as lesões que o agrônomo
 * marca arrastando o mouse ou o dedo. Cada caixa vira um recorte de treino: a IA aprende a
 * lesão, não a folha sadia em volta.
 */
export function MarcadorDeLesoes({
  path,
  caixas,
  onChange,
}: {
  path: string
  caixas: Caixa[]
  onChange: (caixas: Caixa[]) => void
}) {
  const [url, setUrl] = useState<string | null>(null)
  const [falhou, setFalhou] = useState(false)
  const [inicio, setInicio] = useState<{ x: number; y: number } | null>(null)
  const [atual, setAtual] = useState<Caixa | null>(null)
  const area = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const controller = new AbortController()
    let objeto: string | null = null
    setUrl(null)
    setFalhou(false)
    apiBlob(path, controller.signal)
      .then((blob) => {
        objeto = URL.createObjectURL(blob)
        setUrl(objeto)
      })
      .catch(() => {
        if (!controller.signal.aborted) setFalhou(true)
      })
    return () => {
      controller.abort()
      if (objeto) URL.revokeObjectURL(objeto)
    }
  }, [path])

  const ponto = (e: React.PointerEvent) => pontoNormalizado(e.clientX, e.clientY, area.current!.getBoundingClientRect())

  if (falhou) {
    return (
      <div className="grid aspect-[4/3] w-full place-items-center bg-sunken text-[12px] text-muted">
        <ImageOff className="size-5" aria-hidden /> Imagem indisponível
      </div>
    )
  }
  if (!url) return <div className="aspect-[4/3] w-full animate-pulse bg-sunken" />

  return (
    <div className="flex justify-center bg-sunken">
      <div
        ref={area}
        className="relative inline-block cursor-crosshair touch-none select-none"
        onPointerDown={(e) => {
          if (caixas.length >= MAX_LESOES) return
          e.currentTarget.setPointerCapture(e.pointerId)
          setInicio(ponto(e))
        }}
        onPointerMove={(e) => inicio && setAtual(caixaDoArraste(inicio, ponto(e)))}
        onPointerUp={(e) => {
          if (inicio) {
            const caixa = caixaDoArraste(inicio, ponto(e))
            if (caixa) onChange([...caixas, caixa])
          }
          setInicio(null)
          setAtual(null)
        }}
      >
        <img src={url} alt="Folha em revisão: arraste para marcar a lesão" draggable={false} className="block max-h-[70vh] w-auto" />
        {[...caixas, ...(atual ? [atual] : [])].map((c, i) => (
          <div
            key={i}
            className="absolute border-2 border-warning bg-warning/10"
            style={{ left: `${c.x * 100}%`, top: `${c.y * 100}%`, width: `${c.w * 100}%`, height: `${c.h * 100}%` }}
          >
            {i < caixas.length && (
              <button
                type="button"
                aria-label={`Apagar a lesão ${i + 1}`}
                className="absolute -right-2.5 -top-2.5 grid size-5 place-items-center rounded-full bg-surface text-ink shadow"
                onPointerDown={(e) => e.stopPropagation()}
                onClick={() => onChange(caixas.filter((_, j) => j !== i))}
              >
                <X className="size-3" />
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
