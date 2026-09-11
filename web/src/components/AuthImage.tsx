import { ImageOff } from 'lucide-react'
import { useEffect, useState } from 'react'

import { apiBlob } from '@/api/client'
import { cn } from '@/lib/cn'

/**
 * Imagem servida pela API, com o token.
 *
 * Um `<img src>` não manda cabeçalho de autorização, e a foto da lavoura não
 * pode ter URL pública — ela passa pelo escopo do cliente como qualquer dado.
 * Então a imagem é baixada com `fetch` e exibida por uma URL de objeto local.
 */
export function AuthImage({ path, alt, className }: { path: string | null; alt: string; className?: string }) {
  const [url, setUrl] = useState<string | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    if (!path) return
    const controller = new AbortController()
    let objectUrl: string | null = null
    setUrl(null)
    setFailed(false)
    apiBlob(path, controller.signal)
      .then((blob) => {
        objectUrl = URL.createObjectURL(blob)
        setUrl(objectUrl)
      })
      .catch(() => {
        if (!controller.signal.aborted) setFailed(true)
      })
    return () => {
      controller.abort()
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [path])

  if (!path || failed) {
    return (
      <div className={cn('grid place-items-center bg-sunken text-muted', className)}>
        <div className="flex flex-col items-center gap-1 text-[12px]">
          <ImageOff className="size-5" aria-hidden />
          {path ? 'Imagem indisponível' : 'Sem imagem'}
        </div>
      </div>
    )
  }
  if (!url) return <div className={cn('animate-pulse bg-sunken', className)} />
  return <img src={url} alt={alt} className={cn('object-cover', className)} />
}
