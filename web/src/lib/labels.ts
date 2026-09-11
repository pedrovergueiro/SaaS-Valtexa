/**
 * Vocabulário do console em português e a identidade visual de cada coisa.
 *
 * Cores de doença seguem a paleta categórica validada (ver app.css) em **ordem
 * fixa por rótulo**, nunca por posição na lista: a ferrugem é laranja em todo
 * gráfico, filtro ou mapa do sistema. Um rótulo novo — que o agrônomo criou —
 * ocupa o próximo slot livre; passando de oito, dobra em "Outros".
 */

export type Tone = 'good' | 'warning' | 'serious' | 'critical' | 'info' | 'neutral' | 'accent'

const humanize = (value: string) => value.replaceAll('_', ' ').toLowerCase()

function lookup(table: Record<string, string>, value: string | null | undefined): string {
  if (!value) return '—'
  return table[value] ?? humanize(value)
}

// --- missões ------------------------------------------------------------------

const MISSION_STATE: Record<string, string> = {
  draft: 'Rascunho',
  pending_safety: 'Em avaliação',
  blocked: 'Bloqueada',
  authorized: 'Autorizada',
  dispatched: 'Despachada',
  running: 'Em execução',
  paused: 'Pausada',
  paused_for_recharge: 'Recarregando',
  ready_to_resume: 'Pronta para retomar',
  completed: 'Concluída',
  aborted: 'Abortada',
  expired: 'Vencida',
}
const MISSION_STATE_TONE: Record<string, Tone> = {
  draft: 'neutral',
  pending_safety: 'info',
  blocked: 'critical',
  authorized: 'info',
  dispatched: 'info',
  running: 'accent',
  paused: 'warning',
  paused_for_recharge: 'warning',
  ready_to_resume: 'info',
  completed: 'good',
  aborted: 'serious',
  expired: 'neutral',
}
export const missionState = (value: string) => lookup(MISSION_STATE, value)
export const missionStateTone = (value: string): Tone => MISSION_STATE_TONE[value] ?? 'neutral'
export const ACTIVE_MISSION_STATES = new Set([
  'dispatched',
  'running',
  'paused',
  'paused_for_recharge',
  'ready_to_resume',
])

const MISSION_KIND: Record<string, string> = {
  scout: 'Varredura',
  spray: 'Pulverização',
  verify: 'Verificação',
  transit: 'Deslocamento',
}
export const missionKind = (value: string) => lookup(MISSION_KIND, value)

// --- frota --------------------------------------------------------------------

const DEVICE_KIND: Record<string, string> = {
  rover: 'Rover',
  drone: 'Drone',
  dock: 'Base',
  sensor: 'Sensor',
  gateway: 'Gateway',
}
export const deviceKind = (value: string) => lookup(DEVICE_KIND, value)

const DEVICE_STATUS: Record<string, string> = {
  unprovisioned: 'Não provisionado',
  active: 'Ativo',
  maintenance: 'Manutenção',
  suspended: 'Suspenso',
  retired: 'Aposentado',
}
const DEVICE_STATUS_TONE: Record<string, Tone> = {
  unprovisioned: 'neutral',
  active: 'good',
  maintenance: 'warning',
  suspended: 'critical',
  retired: 'neutral',
}
export const deviceStatus = (value: string) => lookup(DEVICE_STATUS, value)
export const deviceStatusTone = (value: string): Tone => DEVICE_STATUS_TONE[value] ?? 'neutral'

const CONNECTIVITY: Record<string, string> = { ok: 'Online', degraded: 'Instável', offline: 'Offline' }
const CONNECTIVITY_TONE: Record<string, Tone> = { ok: 'good', degraded: 'warning', offline: 'neutral' }
export const connectivity = (value: string) => lookup(CONNECTIVITY, value)
export const connectivityTone = (value: string): Tone => CONNECTIVITY_TONE[value] ?? 'neutral'

// --- diagnóstico --------------------------------------------------------------

const DIAGNOSIS_STATUS: Record<string, string> = {
  pending: 'Pendente',
  ai_validated: 'Validado pela IA',
  needs_review: 'Aguardando agrônomo',
  inconclusive: 'Inconclusivo',
  human_confirmed: 'Confirmado',
  human_rejected: 'Rejeitado',
}
const DIAGNOSIS_TONE: Record<string, Tone> = {
  pending: 'neutral',
  ai_validated: 'info',
  needs_review: 'warning',
  inconclusive: 'neutral',
  human_confirmed: 'good',
  human_rejected: 'serious',
}
export const diagnosisStatus = (value: string | null | undefined) => lookup(DIAGNOSIS_STATUS, value)
export const diagnosisTone = (value: string | null | undefined): Tone =>
  (value && DIAGNOSIS_TONE[value]) || 'neutral'

const AGREEMENT: Record<string, string> = {
  agree: 'as análises concordam',
  disagree: 'as análises discordam',
  abstain: 'ao menos uma ficou abaixo do limiar de confiança',
  unavailable: 'só uma análise respondeu',
}
export const agreement = (value: string | null | undefined) => lookup(AGREEMENT, value)

const DECISION: Record<string, string> = {
  no_action: 'Nada a fazer',
  observe: 'Observar',
  need_more_data: 'Coletar mais dados',
  human_review: 'Revisão humana',
  application_candidate: 'Candidata a aplicação',
}
const DECISION_TONE: Record<string, Tone> = {
  no_action: 'good',
  observe: 'info',
  need_more_data: 'neutral',
  human_review: 'warning',
  application_candidate: 'serious',
}
export const decisionOutcome = (value: string) => lookup(DECISION, value)
export const decisionTone = (value: string): Tone => DECISION_TONE[value] ?? 'neutral'

const DISEASE: Record<string, string> = {
  Healthy: 'Saudável',
  Common_Rust: 'Ferrugem comum',
  Blight: 'Helmintosporiose',
  Gray_Leaf_Spot: 'Cercosporiose',
  Rust: 'Ferrugem',
  Cercospora_Leaf_Spot: 'Cercosporiose (café)',
  Phoma_Leaf_Spot: 'Mancha de phoma',
  Leaf_Miner_Damage: 'Bicho-mineiro',
  Other: 'Outros',
}
export const disease = (value: string | null | undefined) => {
  if (!value) return '—'
  return DISEASE[value] ?? value.replaceAll('_', ' ')
}

/** Rótulos do catálogo, sugeridos ao agrônomo — mas ele pode escrever outro. */
export const KNOWN_LABELS = [
  'Healthy',
  'Common_Rust',
  'Blight',
  'Gray_Leaf_Spot',
  'Rust',
  'Cercospora_Leaf_Spot',
  'Phoma_Leaf_Spot',
  'Leaf_Miner_Damage',
]

// --- cores de série -------------------------------------------------------------

const FIXED_SLOT: Record<string, number> = {
  Blight: 1,
  Phoma_Leaf_Spot: 1,
  Common_Rust: 2,
  Rust: 2,
  Healthy: 3,
  Leaf_Miner_Damage: 4,
  Cercospora_Leaf_Spot: 5,
  Gray_Leaf_Spot: 7,
}
const FREE_ORDER = [6, 8, 4, 5, 7, 1, 2, 3]

export const seriesColor = (slot: number) =>
  slot >= 1 && slot <= 8 ? `var(--series-${slot})` : 'var(--series-other)'

/**
 * Slot de cada rótulo presente. Conhecidos têm slot fixo; os demais ocupam os
 * livres, na ordem em que aparecem. Passando de oito, `0` = "Outros".
 */
export function assignSlots(labels: string[]): Map<string, number> {
  const slots = new Map<string, number>()
  const taken = new Set<number>()
  for (const label of labels) {
    const fixed = FIXED_SLOT[label]
    if (fixed !== undefined && !taken.has(fixed)) {
      slots.set(label, fixed)
      taken.add(fixed)
    }
  }
  for (const label of labels) {
    if (slots.has(label)) continue
    const free = FREE_ORDER.find((slot) => !taken.has(slot))
    slots.set(label, free ?? 0)
    if (free !== undefined) taken.add(free)
  }
  return slots
}

/** Ordena rótulos pelo slot — é a ordem em que a paleta foi validada em pilha. */
export function bySlot(labels: string[], slots: Map<string, number>): string[] {
  return [...labels].sort((a, b) => (slots.get(a) || 99) - (slots.get(b) || 99))
}

// --- mapa: três classes, as únicas que a paleta valida em todos os pares --------

export type HealthClass = 'healthy' | 'disease' | 'review'

export const HEALTH: Record<HealthClass, { label: string; color: string }> = {
  healthy: { label: 'Saudável', color: 'var(--series-3)' },
  disease: { label: 'Doença', color: 'var(--series-2)' },
  review: { label: 'Aguardando agrônomo', color: 'var(--series-1)' },
}

export function healthClass(label: string | null | undefined, status: string | null | undefined): HealthClass {
  if (!status || status === 'needs_review' || status === 'inconclusive' || status === 'pending') {
    return 'review'
  }
  return label === 'Healthy' ? 'healthy' : 'disease'
}

// --- insumos, aplicação, pessoas ------------------------------------------------

const CROP: Record<string, string> = { corn: 'Milho', coffee: 'Café', soy: 'Soja', milho: 'Milho' }
export const crop = (value: string) => lookup(CROP, value)

const ROLE: Record<string, string> = {
  owner: 'Proprietário',
  admin: 'Administrador',
  agronomist: 'Agrônomo',
  operator: 'Operador',
  technician: 'Técnico',
  auditor: 'Auditor',
  viewer: 'Leitura',
}
export const role = (value: string | null | undefined) => lookup(ROLE, value)
export const ROLES = Object.keys(ROLE)

const TANK: Record<string, string> = { empty: 'Vazio', loaded: 'Carregado', sealed: 'Lacrado', fault: 'Falha' }
export const tankStatus = (value: string) => lookup(TANK, value)

const APPLICATION: Record<string, string> = { started: 'Em andamento', completed: 'Concluída', aborted: 'Interrompida' }
export const applicationState = (value: string) => lookup(APPLICATION, value)

const VERIFICATION: Record<string, string> = {
  pending: 'Aguardando segunda passada',
  improved: 'Melhorou',
  unchanged: 'Sem mudança',
  worsened: 'Piorou',
  inconclusive: 'Inconclusiva',
}
const VERIFICATION_TONE: Record<string, Tone> = {
  pending: 'neutral',
  improved: 'good',
  unchanged: 'warning',
  worsened: 'critical',
  inconclusive: 'neutral',
}
export const verification = (value: string) => lookup(VERIFICATION, value)
export const verificationTone = (value: string): Tone => VERIFICATION_TONE[value] ?? 'neutral'

const SEVERITY_TONE: Record<string, Tone> = { critical: 'critical', warning: 'warning', info: 'info' }
const SEVERITY: Record<string, string> = { critical: 'Crítico', warning: 'Atenção', info: 'Informação' }
export const severity = (value: string) => lookup(SEVERITY, value)
export const severityTone = (value: string): Tone => SEVERITY_TONE[value] ?? 'neutral'

// --- segurança ------------------------------------------------------------------

const SAFETY_CHECK: Record<string, string> = {
  device_exists: 'Dispositivo cadastrado',
  device_active: 'Dispositivo ativo',
  device_tenant: 'Dispositivo do cliente',
  device_kind: 'Tipo de dispositivo',
  device_capability: 'Capacidades do hardware',
  device_free: 'Sem outra missão em curso',
  battery: 'Bateria',
  rtk: 'Posicionamento RTK',
  mission_state: 'Estado da missão',
  mission_not_expired: 'Validade da missão',
  geometry_valid: 'Polígono válido',
  geofence: 'Cerca virtual',
  approval: 'Aprovação do agrônomo',
  approver_role: 'Papel de quem aprovou',
  product_present: 'Produto definido',
  product_active: 'Produto ativo',
  product_registered: 'Registro no MAPA',
  product_crop: 'Produto autorizado para a cultura',
  batch_valid: 'Lote válido',
  tank_present: 'Tanque definido',
  tank_device: 'Tanque do dispositivo',
  tank_content: 'Conteúdo do tanque',
  tank_volume: 'Volume no tanque',
  rate_range: 'Dose dentro da bula',
  weather: 'Vento',
}
export const safetyCheck = (code: string) => lookup(SAFETY_CHECK, code)

const EVENT: Record<string, string> = {
  'mission.created': 'Missão criada',
  'mission.authorized': 'Missão autorizada',
  'mission.dispatched': 'Missão despachada',
  'mission.started': 'Missão iniciada',
  'mission.paused': 'Missão pausada',
  'mission.resumed': 'Missão pronta para retomar',
  'mission.completed': 'Missão concluída',
  'mission.aborted': 'Missão abortada',
  'mission.expired': 'Missão vencida',
  'safety.blocked': 'Segurança bloqueou uma missão',
  'safety.approved': 'Segurança aprovou uma missão',
  'diagnosis.created': 'Novo diagnóstico',
  'diagnosis.reviewed': 'Diagnóstico revisado',
  'novelty.detected': 'Algo fora do catálogo',
  'application.started': 'Aplicação iniciada',
  'application.completed': 'Aplicação concluída',
  'application.out_of_bounds': 'Aplicação fora da área autorizada',
  'verification.scheduled': 'Verificação agendada',
  'verification.completed': 'Verificação concluída',
  'device.provisioned': 'Dispositivo provisionado',
  'device.offline': 'Dispositivo sem contato',
  'device.fault': 'Falha em dispositivo',
}
export const eventName = (value: string) => EVENT[value] ?? value
