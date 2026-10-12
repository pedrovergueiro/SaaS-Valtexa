import { Loader2, MapPin, Search } from 'lucide-react'
import { useState } from 'react'

import { useBuscaLugar } from '@/api/queries'
import { Button, ErrorBox } from '@/components/ui'
import { type Lugar, leia } from '@/lib/localizar'

/**
 * "Endereço ou coordenadas": o primeiro passo do talhão de um cliente novo.
 *
 * Coordenada, graus-minutos-segundos e link do Google Maps vão direto (sem rede);
 * três pontos ou mais viram contorno; o resto é endereço e vai ao servidor
 * (Google quando ligado, se não OpenStreetMap). Um resultado só leva o mapa direto;
 * vários aparecem para escolher.
 */
export function BuscaDeLugar({
  onLugar,
  onContorno,
  className,
}: {
  onLugar: (lugar: Lugar) => void
  onContorno?: (pontos: number[][]) => void
  className?: string
}) {
  const [texto, setTexto] = useState('')
  const [opcoes, setOpcoes] = useState<Lugar[] | null>(null)
  const [recado, setRecado] = useState<string | null>(null)
  const busca = useBuscaLugar()

  async function ir() {
    setOpcoes(null)
    setRecado(null)
    const lido = leia(texto)
    if (lido.tipo === 'curto') return setRecado('Digite o endereço, a cidade, o nome da fazenda ou as coordenadas.')
    if (lido.tipo === 'ponto') return onLugar(lido.lugar)
    if (lido.tipo === 'contorno') {
      if (onContorno) return onContorno(lido.pontos)
      const [lon = 0, lat = 0] = lido.pontos[0]!
      return onLugar({
        nome: 'Primeiro ponto colado',
        lat,
        lon,
        tipo: 'coordenada',
        fonte: 'coordenadas',
        caixa: null,
      })
    }
    try {
      const { lugares, avisos } = await busca.mutateAsync(lido.texto)
      if (avisos.length) setRecado(avisos.join(' '))
      if (!lugares.length) {
        setRecado('Nada encontrado. Tente a cidade, ou cole a coordenada ou o link do Google Maps da sede.')
      } else if (lugares.length === 1) {
        const unico = lugares[0]!
        if (unico.fonte === 'osm') setRecado(`${unico.nome} · endereço © colaboradores do OpenStreetMap`)
        onLugar(unico)
      } else {
        setOpcoes(lugares)
      }
    } catch {
      /* o erro aparece no ErrorBox */
    }
  }

  return (
    <div className={className}>
      <form
        className="flex gap-2"
        onSubmit={(evento) => {
          evento.preventDefault()
          void ir()
        }}
      >
        <label className="relative flex-1">
          <span className="sr-only">Endereço ou coordenadas</span>
          <Search
            className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted"
            aria-hidden
          />
          <input
            className="input w-full pl-9"
            value={texto}
            onChange={(evento) => setTexto(evento.target.value)}
            placeholder="Endereço, cidade, fazenda, coordenada ou link do Google Maps"
          />
        </label>
        <Button type="submit" variant="primary" disabled={busca.isPending}>
          {busca.isPending ? (
            <Loader2 className="size-4 animate-spin" aria-hidden />
          ) : (
            <MapPin className="size-4" aria-hidden />
          )}
          Ir
        </Button>
      </form>
      <ErrorBox error={busca.error} className="mt-2" />
      {recado && <p className="mt-2 text-[12px] text-ink-2">{recado}</p>}
      {opcoes && (
        <ul
          className="mt-2 divide-y divide-line-soft overflow-hidden rounded-lg border border-line"
          role="listbox"
          aria-label="Lugares encontrados"
        >
          {opcoes.map((lugar) => (
            <li key={`${lugar.lat}:${lugar.lon}:${lugar.nome}`}>
              <button
                type="button"
                role="option"
                aria-selected={false}
                className="w-full px-3 py-2 text-left text-[13px] hover:bg-raised"
                onClick={() => {
                  setOpcoes(null)
                  onLugar(lugar)
                }}
              >
                {lugar.nome}
                {lugar.tipo && <span className="ml-1.5 text-[12px] text-muted">{lugar.tipo}</span>}
              </button>
            </li>
          ))}
        </ul>
      )}
      {opcoes?.some((lugar) => lugar.fonte === 'osm') && (
        <p className="mt-1 text-[11px] text-muted">Endereços © colaboradores do OpenStreetMap</p>
      )}
    </div>
  )
}
