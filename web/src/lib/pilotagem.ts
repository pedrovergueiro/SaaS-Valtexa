/**
 * Estação de pilotagem: controle de videogame, teclado e vídeo ao vivo.
 *
 * Tudo aqui é lógica pura (testada em pilotagem.test.ts); a tela só lê o controle e
 * desenha. Regras de segurança que valem para qualquer fonte de comando:
 *
 * - **homem-morto**: no controle de videogame o Rover só anda com um gatilho de ombro
 *   (LB ou RB) segurado; soltou, o ponto vai a zero. No teclado, segurar a tecla é o
 *   próprio homem-morto. No servidor, cada ponto vale 1 s de qualquer jeito;
 * - **B (ou espaço) = PARAR**: manda o comando de parada assinado, não só zera o ponto;
 * - perdeu o foco da janela, desconectou o controle → zero.
 */

/** Índices do mapeamento "standard" da Gamepad API (Xbox/PlayStation pelo navegador). */
export const BOTOES = { A: 0, B: 1, X: 2, Y: 3, LB: 4, RB: 5, LT: 6, RT: 7, START: 9, CIMA: 12, BAIXO: 13 } as const
export const EIXOS = { ESQ_X: 0, ESQ_Y: 1, DIR_X: 2, DIR_Y: 3 } as const

export const ZONA_MORTA = 0.12
export const EXPO = 0.45

export type ControleBruto = {
  axes: readonly number[]
  buttons: readonly { pressed: boolean; value: number }[]
}

export type LeituraDoControle = {
  /** direita positivo, em [-1, 1], já com zona morta e curva */
  x: number
  /** frente positivo */
  y: number
  homemMorto: boolean
  /** botões que acabaram de ser apertados (borda de subida) */
  parar: boolean
  marchaMais: boolean
  marchaMenos: boolean
  cameraProxima: boolean
  cameraAnterior: boolean
}

/** Zona morta com reescala (sem salto na borda) e curva expo (precisão perto do centro). */
export function eixo(v: number, zona = ZONA_MORTA, expo = EXPO): number {
  if (!Number.isFinite(v)) return 0
  const a = Math.abs(v)
  if (a <= zona) return 0
  const r = Math.min(1, (a - zona) / (1 - zona))
  const curvado = (1 - expo) * r + expo * r ** 3
  return Math.round(Math.sign(v) * curvado * 1000) / 1000
}

const apertado = (c: ControleBruto, i: number) => Boolean(c.buttons[i]?.pressed)

/**
 * Lê o controle: acelerador no analógico esquerdo (vertical), direção no direito
 * (horizontal) — o jeito de dirigir carro de controle remoto e robô de campo.
 */
export function lerControle(c: ControleBruto, anterior?: ControleBruto | null): LeituraDoControle {
  const borda = (i: number) => apertado(c, i) && !(anterior && apertado(anterior, i))
  return {
    x: eixo(c.axes[EIXOS.DIR_X] ?? 0),
    y: -eixo(c.axes[EIXOS.ESQ_Y] ?? 0) || 0, // no controle, para cima é negativo
    homemMorto: apertado(c, BOTOES.LB) || apertado(c, BOTOES.RB),
    parar: borda(BOTOES.B),
    marchaMais: borda(BOTOES.CIMA),
    marchaMenos: borda(BOTOES.BAIXO),
    cameraProxima: borda(BOTOES.Y),
    cameraAnterior: borda(BOTOES.X),
  }
}

export type Fonte = 'controle' | 'joystick' | 'teclado' | 'nenhuma'

/** Quem manda agora: o controle com homem-morto, depois o joystick da tela, depois o teclado. */
export function fonteAtiva(e: {
  controle?: LeituraDoControle | null
  joystick: { x: number; y: number }
  teclado: { x: number; y: number }
}): { fonte: Fonte; x: number; y: number } {
  if (e.controle?.homemMorto && (e.controle.x !== 0 || e.controle.y !== 0)) {
    return { fonte: 'controle', x: e.controle.x, y: e.controle.y }
  }
  if (e.joystick.x !== 0 || e.joystick.y !== 0) return { fonte: 'joystick', ...e.joystick }
  if (e.teclado.x !== 0 || e.teclado.y !== 0) return { fonte: 'teclado', ...e.teclado }
  return { fonte: 'nenhuma', x: 0, y: 0 }
}

export const MARCHAS = [0.1, 0.25, 0.5, 0.75, 1] as const

export function trocaMarcha(atual: number, passo: 1 | -1): number {
  const i = MARCHAS.findIndex((m) => m >= atual - 1e-9)
  const j = Math.min(MARCHAS.length - 1, Math.max(0, (i < 0 ? MARCHAS.length - 1 : i) + passo))
  return MARCHAS[j]!
}

/** Idade do quadro ao vivo, em ms (null se o robô não disse quando capturou). */
export function idadeDoQuadro(capturadoEm: string | null | undefined, agoraMs: number): number | null {
  if (!capturadoEm) return null
  const t = Date.parse(capturadoEm)
  return Number.isFinite(t) ? Math.max(0, agoraMs - t) : null
}

export function tomDaIdade(ms: number | null): 'good' | 'warning' | 'critical' | 'neutral' {
  if (ms == null) return 'neutral'
  if (ms < 700) return 'good'
  if (ms < 2000) return 'warning'
  return 'critical'
}

export function rotuloDaIdade(ms: number | null): string {
  if (ms == null) return 'sem horário'
  return ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toLocaleString('pt-BR', { maximumFractionDigits: 1 })} s`
}

/** Câmera seguinte/anterior na lista (dá a volta). */
export function proximaCamera(cameras: readonly string[], atual: string | null, passo: 1 | -1): string | null {
  if (cameras.length === 0) return null
  const i = atual ? cameras.indexOf(atual) : -1
  return cameras[(((i < 0 ? 0 : i + passo) % cameras.length) + cameras.length) % cameras.length]!
}
