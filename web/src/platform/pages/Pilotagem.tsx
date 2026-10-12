import { Gamepad2, Keyboard, OctagonX, Video, VideoOff } from 'lucide-react'
import { type PointerEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { Badge, Button, Card, CardHeader } from '@/components/ui'
import { type Limits, type Setpoint, TELEOP_PERIOD_MS, isMoving, joystickToSetpoint, keysToAxes } from '@/lib/comando'
import { trechos } from '@/lib/enlace'
import { fmt } from '@/lib/format'
import {
  type ControleBruto,
  type Fonte,
  type LeituraDoControle,
  MARCHAS,
  fonteAtiva,
  idadeDoQuadro,
  lerControle,
  proximaCamera,
  rotuloDaIdade,
  tomDaIdade,
  trocaMarcha,
} from '@/lib/pilotagem'
import { type QuadroAoVivo, type RoverPanel, fetchQuadroAoVivo, sendTeleop, startVideo, stopTeleop, stopVideo } from '@/platform/api'

/**
 * Estação de pilotagem: o vídeo ao vivo das câmeras, o controle de videogame, o teclado e
 * o joystick da tela no mesmo lugar, com o painel de voo (HUD) por cima da imagem.
 *
 * O vídeo vem do Rover pelo mesmo canal assinado do resto (inclusive pela base da
 * fazenda, num slot "só o último vale"); a idade de cada quadro aparece na tela. Dirigir
 * exige o modo Manual; com o controle de videogame, um gatilho de ombro (LB/RB) é o
 * homem-morto. B ou espaço manda PARAR (comando assinado).
 */

type Manda = (kind: string, params?: Record<string, unknown>, ok?: string) => void

const QUALIDADES = [
  { rotulo: 'leve', lado: 480, fps: 3 },
  { rotulo: 'normal', lado: 640, fps: 5 },
  { rotulo: 'alta', lado: 960, fps: 6 },
] as const

const TOM_TEXTO: Record<string, string> = {
  good: 'text-good',
  warning: 'text-warning',
  critical: 'text-critical',
  neutral: 'text-[#9cc9b2]',
}

function camerasDoPainel(painel: RoverPanel): string[] {
  const saude = (painel.health ?? {}) as { cameras?: { id: string }[] }
  return (saude.cameras ?? []).map((c) => c.id).filter(Boolean)
}

// --- controle de videogame -------------------------------------------------------------

function useControle(onLeitura: (l: LeituraDoControle) => void) {
  const leitura = useRef<LeituraDoControle | null>(null)
  const anterior = useRef<ControleBruto | null>(null)
  const [nome, setNome] = useState<string | null>(null)
  const nomeRef = useRef<string | null>(null)
  const cb = useRef(onLeitura)
  cb.current = onLeitura

  useEffect(() => {
    if (typeof navigator === 'undefined' || !navigator.getGamepads) return
    let raf = 0
    const laco = () => {
      const gp = Array.from(navigator.getGamepads()).find((g) => g?.connected) ?? null
      if (gp) {
        const l = lerControle(gp, anterior.current)
        anterior.current = { axes: [...gp.axes], buttons: gp.buttons.map((b) => ({ pressed: b.pressed, value: b.value })) }
        leitura.current = l
        cb.current(l)
        if (nomeRef.current !== gp.id) {
          nomeRef.current = gp.id
          setNome(gp.id)
        }
      } else if (nomeRef.current !== null) {
        leitura.current = null
        anterior.current = null
        nomeRef.current = null
        setNome(null)
      }
      raf = requestAnimationFrame(laco)
    }
    raf = requestAnimationFrame(laco)
    return () => cancelAnimationFrame(raf)
  }, [])

  return { leitura, nome }
}

// --- vídeo ao vivo ---------------------------------------------------------------------

function useVideoAoVivo(id: string, cameras: string[], fps: number, lado: number, ligado: boolean) {
  const [quadros, setQuadros] = useState<Record<string, QuadroAoVivo>>({})
  const [erro, setErro] = useState<string | null>(null)
  const [fpsReal, setFpsReal] = useState<Record<string, number>>({})
  const chegadas = useRef<Record<string, number[]>>({})
  const chave = cameras.join('|')

  // Liga e renova o pedido; fechou a tela, o pedido vence e o Rover para sozinho.
  useEffect(() => {
    if (!ligado || cameras.length === 0) return
    let vivo = true
    const renova = () =>
      startVideo(id, cameras, fps, lado)
        .then(() => vivo && setErro(null))
        .catch((e: Error) => vivo && setErro(e.message))
    renova()
    const t = setInterval(renova, 5_000)
    return () => {
      vivo = false
      clearInterval(t)
      stopVideo(id).catch(() => undefined)
    }
  }, [id, ligado, chave, fps, lado])

  // Busca o último quadro de cada câmera no ritmo pedido.
  useEffect(() => {
    if (!ligado || cameras.length === 0) return
    const ctrl = new AbortController()
    const periodo = Math.max(100, 1000 / fps)
    for (const cam of cameras) {
      void (async () => {
        let ultimoSeq: number | null = null
        while (!ctrl.signal.aborted) {
          const t0 = performance.now()
          try {
            const q = await fetchQuadroAoVivo(id, cam, ctrl.signal)
            if (q && q.seq !== ultimoSeq) {
              ultimoSeq = q.seq
              const lista = (chegadas.current[cam] = [...(chegadas.current[cam] ?? []), q.recebidoEm].filter((t) => q.recebidoEm - t < 3_000))
              setFpsReal((f) => ({ ...f, [cam]: lista.length / 3 }))
              setQuadros((atual) => {
                const velho = atual[cam]
                if (velho) URL.revokeObjectURL(velho.url)
                return { ...atual, [cam]: q }
              })
            } else if (q) {
              URL.revokeObjectURL(q.url) // o mesmo quadro de antes
            }
          } catch (e) {
            if (ctrl.signal.aborted) return
            setErro((e as Error).message)
          }
          const resta = periodo - (performance.now() - t0)
          await new Promise((r) => setTimeout(r, Math.max(30, resta)))
        }
      })()
    }
    return () => ctrl.abort()
  }, [id, ligado, chave, fps])

  // Ao sair, solta as imagens da memória.
  useEffect(
    () => () => {
      setQuadros((atual) => {
        Object.values(atual).forEach((q) => URL.revokeObjectURL(q.url))
        return {}
      })
    },
    [],
  )

  return { quadros, erro, fpsReal }
}

// --- estação ---------------------------------------------------------------------------

export function EstacaoDePilotagem({ painel, id, pode, manda }: { painel: RoverPanel; id: string; pode: boolean; manda: Manda }) {
  const limites: Limits & { validity_s: number } = painel.teleop_limits
  const habilitado = pode && painel.control_mode === 'manual'
  const cameras = useMemo(() => camerasDoPainel(painel), [painel])
  const [principal, setPrincipal] = useState<string | null>(null)
  const [mosaico, setMosaico] = useState(false)
  const [qualidade, setQualidade] = useState(1)
  const [videoLigado, setVideoLigado] = useState(true)
  const [marcha, setMarcha] = useState(0.5)
  const [teclado, setTeclado] = useState(false)
  const [erro, setErro] = useState<string | null>(null)
  const [enviado, setEnviado] = useState<Setpoint>({ v: 0, w: 0 })
  const [mostra, setMostra] = useState<{ fonte: Fonte; ponto: Setpoint }>({ fonte: 'nenhuma', ponto: { v: 0, w: 0 } })
  const [agora, setAgora] = useState(() => Date.now())

  const joystick = useRef({ x: 0, y: 0 })
  const tecladoEixos = useRef({ x: 0, y: 0 })
  const marchaRef = useRef(marcha)
  marchaRef.current = marcha

  const atual = principal && cameras.includes(principal) ? principal : (cameras[0] ?? null)
  const pedidas = useMemo(
    () => (atual ? (mosaico ? [atual, ...cameras.filter((c) => c !== atual)].slice(0, 4) : [atual]) : []),
    [atual, mosaico, cameras],
  )
  const q = QUALIDADES[qualidade]!
  const { quadros, erro: erroVideo, fpsReal } = useVideoAoVivo(id, pedidas, q.fps, q.lado, videoLigado && pedidas.length > 0)

  const parar = useCallback(() => {
    joystick.current = { x: 0, y: 0 }
    tecladoEixos.current = { x: 0, y: 0 }
    stopTeleop(id).catch(() => undefined)
    manda('parar', { motivo: 'PARAR na estação de pilotagem' }, 'Parada enviada')
  }, [id, manda])

  // Botões do controle (borda de subida): PARAR, marcha, câmera.
  const { leitura, nome: controle } = useControle((l) => {
    if (l.parar) parar()
    if (l.marchaMais) setMarcha((m) => trocaMarcha(m, 1))
    if (l.marchaMenos) setMarcha((m) => trocaMarcha(m, -1))
    if (l.cameraProxima) setPrincipal((c) => proximaCamera(cameras, c ?? atual, 1))
    if (l.cameraAnterior) setPrincipal((c) => proximaCamera(cameras, c ?? atual, -1))
  })

  // Laço de comando: a cada 250 ms decide quem manda e envia; parou, manda "pare" uma vez.
  useEffect(() => {
    if (!habilitado) return
    let andava = false
    let vivo = true
    const tick = () => {
      const f = fonteAtiva({ controle: leitura.current, joystick: joystick.current, teclado: tecladoEixos.current })
      const ponto = joystickToSetpoint(f.x, f.y, limites, marchaRef.current)
      setMostra({ fonte: f.fonte, ponto })
      if (isMoving(ponto)) {
        andava = true
        sendTeleop(id, ponto.v, ponto.w)
          .then(() => vivo && (setEnviado(ponto), setErro(null)))
          .catch((e: Error) => vivo && setErro(e.message))
      } else if (andava) {
        andava = false
        stopTeleop(id).catch(() => undefined)
        setEnviado({ v: 0, w: 0 })
      }
    }
    const t = setInterval(tick, TELEOP_PERIOD_MS)
    return () => {
      vivo = false
      clearInterval(t)
      if (andava) stopTeleop(id).catch(() => undefined)
      setEnviado({ v: 0, w: 0 })
    }
  }, [habilitado, id, limites, leitura])

  // Teclado: W A S D / setas (segurar = homem-morto), espaço = PARAR, Q/E = marcha.
  useEffect(() => {
    if (!teclado || !habilitado) return
    const apertadas = new Set<string>()
    const atualiza = () => (tecladoEixos.current = keysToAxes(apertadas))
    const desce = (e: KeyboardEvent) => {
      const k = e.key.toLowerCase()
      if (['w', 'a', 's', 'd', 'arrowup', 'arrowdown', 'arrowleft', 'arrowright'].includes(k)) {
        e.preventDefault()
        apertadas.add(k)
        atualiza()
      } else if (k === ' ') {
        e.preventDefault()
        apertadas.clear()
        atualiza()
        parar()
      } else if (k === 'e') setMarcha((m) => trocaMarcha(m, 1))
      else if (k === 'q') setMarcha((m) => trocaMarcha(m, -1))
    }
    const sobe = (e: KeyboardEvent) => {
      apertadas.delete(e.key.toLowerCase())
      atualiza()
    }
    const perdeu = () => {
      apertadas.clear()
      atualiza()
    }
    window.addEventListener('keydown', desce)
    window.addEventListener('keyup', sobe)
    window.addEventListener('blur', perdeu)
    return () => {
      window.removeEventListener('keydown', desce)
      window.removeEventListener('keyup', sobe)
      window.removeEventListener('blur', perdeu)
      tecladoEixos.current = { x: 0, y: 0 }
    }
  }, [teclado, habilitado, parar])

  // Relógio da tela (idade dos quadros).
  useEffect(() => {
    const t = setInterval(() => setAgora(Date.now()), 250)
    return () => clearInterval(t)
  }, [])

  const quadro = atual ? quadros[atual] : undefined
  const idade = quadro ? idadeDoQuadro(quadro.capturadoEm, agora) : null
  const ultima = painel.telemetry.at(-1)
  const caminho = trechos(painel.caminho)

  return (
    <Card className="overflow-hidden p-0">
      <div className="px-5 pt-4">
        <CardHeader
          title={
            <span className="flex items-center gap-2">
              <Gamepad2 className="size-4" /> Estação de pilotagem
            </span>
          }
          subtitle={`Vídeo ao vivo e controle no mesmo lugar. Até ${limites.v_ms} m/s e ${limites.w_rad_s} rad/s; cada comando vale ${limites.validity_s} s. Controle de videogame: segure LB ou RB para andar, B para PARAR.`}
        />
      </div>

      {/* vídeo + HUD */}
      <div className="relative aspect-[4/3] w-full bg-black">
        {quadro ? (
          <img src={quadro.url} alt={`Câmera ${atual} ao vivo`} className="size-full object-contain" />
        ) : (
          <div className="grid size-full place-items-center text-[13px] text-[#7fb59a]">
            {cameras.length === 0
              ? 'O rover ainda não informou as câmeras (rode "Testar tudo").'
              : videoLigado
                ? 'Esperando o primeiro quadro…'
                : 'Vídeo desligado.'}
          </div>
        )}
        {/* mira */}
        <div className="pointer-events-none absolute top-1/2 left-1/2 size-8 -translate-x-1/2 -translate-y-1/2 rounded-full border border-white/40" />
        {/* topo: modo, câmera, idade */}
        <div className="pointer-events-none absolute inset-x-0 top-0 flex items-start justify-between gap-2 bg-gradient-to-b from-black/70 to-transparent p-3 text-[12px] text-white">
          <div className="space-y-0.5">
            <div className="font-medium tracking-wide">{atual ?? '—'} · {q.rotulo} {q.lado}px</div>
            <div className={TOM_TEXTO[tomDaIdade(idade)]}>quadro {rotuloDaIdade(idade)} · {fmt.number(atual ? (fpsReal[atual] ?? 0) : 0, 1)} qps</div>
          </div>
          <div className="space-y-0.5 text-right">
            <div>{painel.control_mode ?? 'sem modo'} · fonte: {mostra.fonte}</div>
            <div>
              bateria {painel.device.battery_percent != null ? `${fmt.number(Number(painel.device.battery_percent))}%` : '—'} · RTK {ultima?.rtk_fix ?? '—'}
            </div>
          </div>
        </div>
        {/* base: velocidade, caminho */}
        <div className="pointer-events-none absolute inset-x-0 bottom-0 flex items-end justify-between gap-3 bg-gradient-to-t from-black/75 to-transparent p-3 text-[12px] text-white">
          <div className="num space-y-1">
            <Barra rotulo="v" valor={mostra.ponto.v} max={limites.v_ms} unidade="m/s" />
            <Barra rotulo="ω" valor={mostra.ponto.w} max={limites.w_rad_s} unidade="rad/s" />
            <div className="text-[#9cc9b2]">enviado {fmt.number(enviado.v, 2)} m/s · {fmt.number(enviado.w, 2)} rad/s · marcha {Math.round(marcha * 100)}%</div>
          </div>
          <div className="space-y-0.5 text-right">
            {caminho.map((t) => (
              <div key={t.nome} className={TOM_TEXTO[t.tom]}>
                {t.nome}: {t.detalhe}
              </div>
            ))}
          </div>
        </div>
        {!habilitado && (
          <div className="pointer-events-none absolute top-14 left-1/2 -translate-x-1/2 rounded bg-black/70 px-3 py-1 text-[12px] text-[#9cc9b2]">
            {pode ? 'Só olhando: coloque em Manual para dirigir' : 'Sem permissão para dirigir'}
          </div>
        )}
      </div>

      {/* miniaturas */}
      {cameras.length > 1 && (
        <div className="flex gap-2 overflow-x-auto bg-[#07130e] p-2">
          {cameras.map((c) => {
            const mini = quadros[c]
            return (
              <button
                key={c}
                type="button"
                onClick={() => setPrincipal(c)}
                className={`relative aspect-[4/3] w-28 shrink-0 overflow-hidden rounded border ${c === atual ? 'border-accent' : 'border-[#1d3a2c]'}`}
                aria-label={`Ver a câmera ${c}`}
              >
                {mini ? <img src={mini.url} alt="" className="size-full object-cover" /> : <span className="grid size-full place-items-center text-[10px] text-[#7fb59a]">{c}</span>}
                <span className="absolute bottom-0 left-0 bg-black/60 px-1 text-[10px] text-white">{c}</span>
              </button>
            )
          })}
        </div>
      )}

      {/* controles */}
      <div className="grid gap-4 p-5 md:grid-cols-[auto_1fr]">
        <Joystick ativo={habilitado} onChange={(e) => (joystick.current = e)} />
        <div className="min-w-0 space-y-3 text-[13px]">
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="danger" onClick={parar} disabled={!pode}>
              <OctagonX className="size-4" /> PARAR
            </Button>
            <Button variant="secondary" onClick={() => setVideoLigado((v) => !v)}>
              {videoLigado ? <VideoOff className="size-4" /> : <Video className="size-4" />} {videoLigado ? 'Desligar vídeo' : 'Ligar vídeo'}
            </Button>
            <Badge tone={controle ? 'good' : 'neutral'}>{controle ? `controle: ${controle.slice(0, 28)}` : 'sem controle de videogame'}</Badge>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <label className="flex items-center gap-2">
              Qualidade
              <select className="input" value={qualidade} onChange={(e) => setQualidade(Number(e.target.value))} aria-label="Qualidade do vídeo">
                {QUALIDADES.map((x, i) => (
                  <option key={x.rotulo} value={i}>
                    {x.rotulo} ({x.lado}px, {x.fps} qps)
                  </option>
                ))}
              </select>
            </label>
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={mosaico} onChange={(e) => setMosaico(e.target.checked)} /> Todas as câmeras ao vivo (até 4)
            </label>
          </div>
          <label className="block">
            <span className="text-muted">Marcha: {Math.round(marcha * 100)}% do máximo (controle: ↑/↓; teclado: Q/E)</span>
            <input
              type="range"
              min={0}
              max={MARCHAS.length - 1}
              step={1}
              value={Math.max(0, MARCHAS.findIndex((m) => m >= marcha - 1e-9))}
              onChange={(e) => setMarcha(MARCHAS[Number(e.target.value)]!)}
              className="w-full"
              aria-label="Marcha"
            />
          </label>
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={teclado} disabled={!habilitado} onChange={(e) => setTeclado(e.target.checked)} />
            <Keyboard className="size-4" /> Teclado (W A S D / setas; espaço = PARAR)
          </label>
          <div className="text-[12px] text-muted">
            Controle de videogame: analógico esquerdo acelera, direito vira; LB/RB segurado é o homem-morto; B = PARAR; X/Y trocam a câmera.
            Sem sinal por 1 s o rover para sozinho.
          </div>
          {(erro || erroVideo) && <div className="text-[12px] text-critical">{erro ?? erroVideo}</div>}
          <div className="text-[12px] text-muted">no servidor: {painel.teleop.active ? `controle remoto ativo (seq ${painel.teleop.seq})` : 'parado'}</div>
        </div>
      </div>
    </Card>
  )
}

function Barra({ rotulo, valor, max, unidade }: { rotulo: string; valor: number; max: number; unidade: string }) {
  const f = max > 0 ? Math.max(-1, Math.min(1, valor / max)) : 0
  return (
    <div className="flex items-center gap-2">
      <span className="w-3">{rotulo}</span>
      <div className="relative h-1.5 w-32 rounded bg-white/20">
        <div className="absolute top-0 h-full rounded bg-accent" style={f >= 0 ? { left: '50%', width: `${f * 50}%` } : { right: '50%', width: `${-f * 50}%` }} />
        <div className="absolute top-[-2px] left-1/2 h-[10px] w-px bg-white/60" />
      </div>
      <span>
        {fmt.number(valor, 2)} {unidade}
      </span>
    </div>
  )
}

function Joystick({ ativo, onChange }: { ativo: boolean; onChange: (e: { x: number; y: number }) => void }) {
  const ref = useRef<HTMLDivElement>(null)
  const [pos, setPos] = useState({ x: 0, y: 0 })
  const [segurando, setSegurando] = useState(false)

  const mover = (e: PointerEvent<HTMLDivElement>) => {
    const caixa = ref.current?.getBoundingClientRect()
    if (!caixa) return
    const r = caixa.width / 2
    let x = (e.clientX - (caixa.left + r)) / r
    let y = -(e.clientY - (caixa.top + r)) / r
    const n = Math.hypot(x, y)
    if (n > 1) {
      x /= n
      y /= n
    }
    setPos({ x, y })
    onChange({ x, y })
  }
  const soltar = () => {
    setSegurando(false)
    setPos({ x: 0, y: 0 })
    onChange({ x: 0, y: 0 })
  }

  return (
    <div
      ref={ref}
      role="application"
      aria-label="Joystick: segure e arraste para dirigir"
      className={`relative size-40 touch-none rounded-full border-2 ${ativo ? 'border-accent bg-[#07130e]' : 'border-line bg-sunken opacity-50'} select-none`}
      onPointerDown={(e) => {
        if (!ativo) return
        ;(e.target as HTMLElement).setPointerCapture(e.pointerId)
        setSegurando(true)
        mover(e)
      }}
      onPointerMove={(e) => segurando && mover(e)}
      onPointerUp={soltar}
      onPointerCancel={soltar}
      onLostPointerCapture={soltar}
    >
      <div className="pointer-events-none absolute inset-5 rounded-full border border-dashed border-[#1d3a2c]" />
      <div className="pointer-events-none absolute top-1/2 left-0 h-px w-full bg-[#1d3a2c]" />
      <div className="pointer-events-none absolute top-0 left-1/2 h-full w-px bg-[#1d3a2c]" />
      <div
        className={`pointer-events-none absolute size-12 rounded-full ${segurando ? 'bg-accent' : 'bg-[#3a6b55]'} shadow-lg`}
        style={{ left: `calc(50% + ${pos.x * 40}% - 1.5rem)`, top: `calc(50% - ${pos.y * 40}% - 1.5rem)` }}
      />
      <span className="pointer-events-none absolute top-2 left-1/2 -translate-x-1/2 text-[10px] text-[#7fb59a]">FRENTE</span>
    </div>
  )
}
