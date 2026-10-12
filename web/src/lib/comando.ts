/**
 * Centro de comando do Rover: o que a tela decide (o servidor e o robô decidem o resto).
 *
 * Controle remoto: o operador segura o comando (joystick ou teclas) e a tela renova o
 * ponto de ajuste a cada `TELEOP_PERIOD_MS`; cada ponto vale 1 s no servidor. Soltou,
 * a tela manda "pare" — e, se a rede cair, o ponto vence sozinho (homem-morto).
 */
import type { Tone } from './labels'

export const TELEOP_PERIOD_MS = 250
export const DEADZONE = 0.08

export type Limits = { v_ms: number; w_rad_s: number }
export type Setpoint = { v: number; w: number }

const clamp = (x: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, x))
const round = (x: number, casas = 3) => Math.round(x * 10 ** casas) / 10 ** casas

/**
 * Joystick → velocidade. `x` para a direita e `y` para a frente, em [-1, 1]; `marcha`
 * (0–1) limita a fração do máximo. Giro positivo = para a esquerda (convenção ROS).
 */
export function joystickToSetpoint(x: number, y: number, limits: Limits, marcha = 1): Setpoint {
  const mx = Math.abs(x) < DEADZONE ? 0 : clamp(x, -1, 1)
  const my = Math.abs(y) < DEADZONE ? 0 : clamp(y, -1, 1)
  const fator = clamp(marcha, 0, 1)
  return {
    v: round(my * limits.v_ms * fator) || 0,
    w: round(-mx * limits.w_rad_s * fator) || 0,
  }
}

/** Teclas (W/A/S/D ou setas) → joystick. */
export function keysToAxes(teclas: ReadonlySet<string>): { x: number; y: number } {
  const tem = (...k: string[]) => k.some((t) => teclas.has(t))
  const y = (tem('w', 'arrowup') ? 1 : 0) - (tem('s', 'arrowdown') ? 1 : 0)
  const x = (tem('d', 'arrowright') ? 1 : 0) - (tem('a', 'arrowleft') ? 1 : 0)
  return { x, y }
}

export const isMoving = (s: Setpoint) => s.v !== 0 || s.w !== 0

export const MODES = ['autonomo', 'manual', 'pausado', 'parado'] as const
export type Mode = (typeof MODES)[number]

const MODE_INFO: Record<Mode, { label: string; tone: Tone; hint: string }> = {
  autonomo: { label: 'Autônomo', tone: 'good', hint: 'Segue a rota da missão sozinho.' },
  manual: { label: 'Manual', tone: 'info', hint: 'Só anda pelo controle remoto.' },
  pausado: { label: 'Pausado', tone: 'warning', hint: 'Parado no lugar; a missão espera.' },
  parado: { label: 'Parado', tone: 'critical', hint: 'Parada pedida; não anda até novo modo.' },
}

export function modeInfo(mode: string | null | undefined) {
  return (mode && MODE_INFO[mode as Mode]) || { label: 'Sem modo', tone: 'neutral' as Tone, hint: 'Nenhum modo pedido ainda.' }
}

const COMMAND_LABEL: Record<string, string> = {
  diagnostico: 'Teste de peças',
  foto: 'Foto',
  modo: 'Modo',
  parar: 'Parada',
  config: 'Configuração',
  recarregar_modelos: 'Recarregar modelos',
  reiniciar: 'Reiniciar serviço',
  ensaio: 'Ensaio',
  ensaio_cancelar: 'Cancelar ensaio',
}

export const commandLabel = (kind: string) => COMMAND_LABEL[kind] ?? kind

const STATE: Record<string, { label: string; tone: Tone }> = {
  pendente: { label: 'Aguardando o rover', tone: 'neutral' },
  entregue: { label: 'Executando', tone: 'info' },
  em_execucao: { label: 'Em execução', tone: 'info' },
  concluido: { label: 'Concluído', tone: 'good' },
  falhou: { label: 'Falhou', tone: 'critical' },
  expirado: { label: 'Expirou', tone: 'warning' },
  cancelado: { label: 'Cancelado', tone: 'neutral' },
}

export const commandState = (state: string) => STATE[state] ?? { label: state, tone: 'neutral' as Tone }

/** Resumo de um comando para a lista ("modo autonomo", "gnss, imu"...). */
export function commandSummary(kind: string, params: Record<string, unknown>): string {
  if (kind === 'modo') return String(params.modo ?? '')
  if (kind === 'foto') return String(params.camera_id ?? '')
  if (kind === 'parar') return String(params.motivo ?? '')
  if (kind === 'diagnostico') {
    const pecas = params.pecas as string[] | undefined
    return pecas?.length ? pecas.join(', ') : 'todas as peças'
  }
  if (kind === 'config') return Object.keys((params.rover_json as object) ?? {}).join(', ')
  if (kind === 'ensaio') return String(params.ensaio ?? '')
  return ''
}

const PART_LABEL: Record<string, string> = {
  gnss: 'GPS RTK (ZED-F9P)',
  imu: 'IMU (Xsens, CAN)',
  acelerador: 'IA embarcada (Jetson)',
  sistema: 'Computador (CPU, memória)',
  disco: 'Disco',
  navegacao: 'Navegação',
  lente: 'Correção da lente',
}

export function partLabel(nome: string): string {
  if (nome.startsWith('camera:')) return `Câmera ${nome.slice(7)}`
  return PART_LABEL[nome] ?? nome
}

export type PartResult = { nome: string; label: string; ok: boolean; erro?: string; detalhe: Record<string, unknown> }

/** O laudo do comando `diagnostico` em linhas para a tabela de peças. */
export function partsFromReport(result: unknown): PartResult[] {
  const pecas = (result as { pecas?: Record<string, Record<string, unknown>> } | null)?.pecas
  if (!pecas) return []
  return Object.entries(pecas)
    .map(([nome, v]) => {
      const { ok, erro, jpeg_base64: _foto, ...detalhe } = v
      return { nome, label: partLabel(nome), ok: ok === true, erro: erro as string | undefined, detalhe }
    })
    .sort((a, b) => Number(a.ok) - Number(b.ok) || a.label.localeCompare(b.label))
}

/** A última foto de cada câmera nos resultados de comando (foto ou diagnóstico com fotos). */
export function latestPhotos(
  commands: readonly { kind: string; state: string; result: unknown; finished_at: string | null }[],
): Record<string, { src: string; at: string | null; detalhe: Record<string, unknown> }> {
  const fotos: Record<string, { src: string; at: string | null; detalhe: Record<string, unknown> }> = {}
  for (const c of commands) {
    if (c.state !== 'concluido' || !c.result) continue
    const r = c.result as Record<string, unknown>
    const candidatas: [string, Record<string, unknown>][] =
      c.kind === 'foto'
        ? [[String(r.camera_id), r]]
        : Object.entries((r.pecas as Record<string, Record<string, unknown>>) ?? {})
            .filter(([n]) => n.startsWith('camera:'))
            .map(([n, v]) => [n.slice(7), v])
    for (const [cam, v] of candidatas) {
      if (fotos[cam] || typeof v.jpeg_base64 !== 'string') continue
      const { jpeg_base64, ...detalhe } = v
      fotos[cam] = { src: `data:image/jpeg;base64,${jpeg_base64}`, at: c.finished_at, detalhe }
    }
  }
  return fotos
}

/** Presets de configuração com nome que o técnico reconhece. */
export const CONFIG_PRESETS = [
  {
    id: 'coleta',
    label: 'Modo coleta',
    hint: 'Guarda TODA foto em original (validação de campo, calibração, treino). Usa mais disco e rede.',
    rover_json: { retencao: { normal_sample_every: 1 } },
  },
  {
    id: 'normal',
    label: 'Modo normal',
    hint: 'Foto normal sobe reduzida; só eventos em original. O padrão de operação.',
    rover_json: { retencao: { normal_sample_every: 0 } },
  },
] as const
