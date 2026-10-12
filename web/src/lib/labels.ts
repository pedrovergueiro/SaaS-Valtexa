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
  Northern_Leaf_Blight: 'Helmintosporiose',
  Southern_Rust: 'Ferrugem-polissora',
  Tar_Spot: 'Mancha de alcatrão',
  Spodoptera_frugiperda: 'Lagarta-do-cartucho',
  Dalbulus_maidis: 'Cigarrinha-do-milho',
  Helicoverpa_armigera: 'Helicoverpa',
  Diabrotica_speciosa: 'Vaquinha',
  Dichelops_melacanthus: 'Percevejo barriga-verde',
  Euschistus_heros: 'Percevejo-marrom',
  Anticarsia_gemmatalis: 'Lagarta-da-soja',
  Leucoptera_coffeella: 'Bicho-mineiro',
  Hypothenemus_hampei: 'Broca-do-café',
  // banana
  Sigatoka: 'Sigatoka',
  Fusarium_Wilt: 'Mal-do-Panamá (fusariose)',
  Cordana: 'Mancha de cordana',
  Pestalotiopsis: 'Pestalotiopsis',
  Cosmopolites_sordidus: 'Moleque-da-bananeira',
  // citros
  Algal_Leaf_Spot: 'Mancha de alga',
  Anthracnose: 'Antracnose',
  Black_Spot: 'Pinta-preta',
  Canker: 'Cancro cítrico',
  Curl_Leaf: 'Enrolamento da folha',
  Greening: 'Greening (HLB)',
  Melanose: 'Melanose',
  Scab: 'Verrugose',
  Sooty_Mold: 'Fumagina',
  Leafminer: 'Larva-minadora',
  Mites: 'Ácaros',
  Phyllocnistis_citrella: 'Larva-minadora-dos-citros',
  Diaphorina_citri: 'Psilídeo (Diaphorina)',
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
  'Spodoptera_frugiperda',
  'Dalbulus_maidis',
  'Diabrotica_speciosa',
  'Euschistus_heros',
  'Hypothenemus_hampei',
  'Sigatoka',
  'Fusarium_Wilt',
  'Cordana',
  'Pestalotiopsis',
  'Algal_Leaf_Spot',
  'Anthracnose',
  'Black_Spot',
  'Canker',
  'Curl_Leaf',
  'Greening',
  'Leafminer',
  'Melanose',
  'Mites',
  'Scab',
  'Sooty_Mold',
]

// --- cópia 3D: categoria de cada achado --------------------------------------------

/**
 * O que o produtor procura primeiro na cópia: "tem praga ali?" vem antes de
 * "qual praga?". A categoria vem do servidor (`services/taxonomy.py`).
 */
export const CATEGORY: Record<string, string> = {
  pest: 'Praga',
  disease: 'Doença',
  review: 'Aguardando agrônomo',
  other: 'Outro achado',
  healthy: 'Saudável',
}
export const category = (value: string) => lookup(CATEGORY, value)

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

const CROP: Record<string, string> = {
  corn: 'Milho',
  coffee: 'Café',
  soy: 'Soja',
  milho: 'Milho',
  banana: 'Banana',
  bananeira: 'Banana',
  citrus: 'Citros',
  citros: 'Citros',
  laranja: 'Laranja',
  lemon: 'Limão',
  orange: 'Laranja',
}
export const crop = (value: string) => lookup(CROP, value)

/**
 * Culturas em que o rover chega perto da planta e a inferência junta os quadros
 * por planta — os mesmos apelidos de BANANA e CITRUS em `services/ai_pipeline.py`.
 */
const ROVER_FRAME_CROPS = new Set([
  'banana', 'bananeira', 'banana-prata', 'banana-nanica',
  'citrus', 'citros', 'laranja', 'limão', 'limao', 'lima', 'orange', 'lemon',
])
export const isRoverFrameCrop = (value: string) => ROVER_FRAME_CROPS.has(value.trim().toLowerCase())

// --- IA: portão de enquadramento, zonas da planta, plantas do talhão --------------

/**
 * O que o portão de enquadramento achou que a foto é, quando não é folha. É
 * o que o agrônomo vê para nomear o recorte — e daí sai o dataset de pseudocaule.
 */
const SCENE: Record<string, string> = {
  folha_milho: 'folha de milho',
  folha_cafe: 'folha de café',
  folha_banana: 'folha de bananeira',
  folha_citros: 'folha de citros',
  folha_doente: 'folha com lesões',
  folha: 'folha',
  aereo: 'foto aérea',
  dossel: 'dossel visto de cima',
  colmo: 'colmo',
  planta_inteira: 'planta inteira',
  texto: 'texto ou slide',
  solo: 'solo',
  ceu: 'céu',
  pessoa: 'pessoa',
  maquina: 'máquina',
  fruto: 'fruto',
  pseudocaule: 'pseudocaule',
  tronco: 'tronco',
  fruto_citros: 'fruto de citros',
  corte: 'corte do caule',
}
export const scene = (value: string | null | undefined) => lookup(SCENE, value)

/** Faixas de altura da planta que a câmera do rover cobre (VALTEXA-B/app/rover.py). */
const PLANT_ZONE: Record<string, string> = {
  pseudocaule: 'Pseudocaule',
  folhas_baixas: 'Folhas baixas',
  tronco_e_saia: 'Tronco e saia',
  copa: 'Copa',
}
export const plantZone = (value: string) => lookup(PLANT_ZONE, value)

const PLANT_STATUS: Record<string, string> = {
  sadia: 'Sadia',
  suspeita: 'Suspeita',
  doente: 'Doente',
  revisar: 'Revisar',
}
const PLANT_STATUS_TONE: Record<string, Tone> = {
  sadia: 'good',
  suspeita: 'warning',
  doente: 'serious',
  revisar: 'info',
}
export const plantStatus = (value: string) => lookup(PLANT_STATUS, value)
export const plantStatusTone = (value: string): Tone => PLANT_STATUS_TONE[value] ?? 'neutral'
export const PLANT_STATUSES = Object.keys(PLANT_STATUS)

const MODEL_VARIANT: Record<string, string> = { campo: 'Campo', comercial: 'Comercial' }
export const modelVariant = (value: string) => lookup(MODEL_VARIANT, value)

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
  'row_scan.received': 'Rua escaneada pelo rover',
}
export const eventName = (value: string) => EVENT[value] ?? value

// --- coletas -------------------------------------------------------------------

const COLLECTION_STATE: Record<string, string> = {
  draft: 'Rascunho',
  uploading: 'Enviando',
  upload_completed: 'Upload concluído',
  processing_queued: 'Na fila',
  ai_processing: 'Processando',
  results_generated: 'Resultados gerados',
  review_required: 'Aguardando agrônomo',
  analyzed: 'Analisada',
  available_to_client: 'Disponível ao cliente',
  failed: 'Falhou',
  cancelled: 'Cancelada',
}

const COLLECTION_STATE_TONE: Record<string, Tone> = {
  draft: 'neutral',
  uploading: 'info',
  upload_completed: 'info',
  processing_queued: 'info',
  ai_processing: 'accent',
  results_generated: 'accent',
  review_required: 'warning',
  analyzed: 'good',
  available_to_client: 'good',
  failed: 'critical',
  cancelled: 'neutral',
}

export const collectionState = (value: string | null | undefined) => lookup(COLLECTION_STATE, value)
export const collectionStateTone = (value: string | null | undefined): Tone =>
  COLLECTION_STATE_TONE[value ?? ''] ?? 'neutral'

const COLLECTION_FILE_STATE: Record<string, string> = {
  registered: 'Declarado',
  uploading: 'Enviando',
  stored: 'Guardado',
  processing: 'Processando',
  analyzed: 'Analisado',
  needs_review: 'Para o agrônomo',
  no_model: 'Sem modelo',
  failed: 'Falhou',
  rejected: 'Recusado',
}

const COLLECTION_FILE_TONE: Record<string, Tone> = {
  registered: 'neutral',
  uploading: 'info',
  stored: 'info',
  processing: 'accent',
  analyzed: 'good',
  needs_review: 'warning',
  no_model: 'warning',
  failed: 'critical',
  rejected: 'critical',
}

export const collectionFileState = (value: string | null | undefined) =>
  lookup(COLLECTION_FILE_STATE, value)
export const collectionFileTone = (value: string | null | undefined): Tone =>
  COLLECTION_FILE_TONE[value ?? ''] ?? 'neutral'

const COLLECTION_KIND: Record<string, string> = {
  aerial_image: 'Imagem aérea',
  orthomosaic: 'Ortomosaico',
  ground_image: 'Imagem de solo',
  other: 'Outro',
}

export const collectionKind = (value: string | null | undefined) => lookup(COLLECTION_KIND, value)

const COLLECTION_SOURCE: Record<string, string> = {
  drone_third_party: 'Drone terceirizado',
  rover: 'Rover ValTexa',
  handheld: 'Câmera de mão',
  drone_owned: 'Drone ValTexa (fase futura)',
}

export const collectionSource = (value: string | null | undefined) =>
  lookup(COLLECTION_SOURCE, value)

const PLATFORM: Record<string, string> = {
  aerial: 'Aérea',
  ground: 'Solo',
  any: 'Qualquer',
}

export const capturePlatform = (value: string | null | undefined) => lookup(PLATFORM, value)

const JOB_STATE: Record<string, string> = {
  queued: 'Na fila',
  running: 'Executando',
  done: 'Concluído',
  failed: 'Falhou',
  cancelled: 'Cancelado',
}

const JOB_TONE: Record<string, Tone> = {
  queued: 'info',
  running: 'accent',
  done: 'good',
  failed: 'critical',
  cancelled: 'neutral',
}

export const jobState = (value: string | null | undefined) => lookup(JOB_STATE, value)
export const jobStateTone = (value: string | null | undefined): Tone =>
  JOB_TONE[value ?? ''] ?? 'neutral'

/** Tamanho em bytes, na escala que couber. Coleta se mede em GB. */
export function bytes(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  const escala = ['B', 'kB', 'MB', 'GB', 'TB']
  let restante = value
  let passo = 0
  while (restante >= 1024 && passo < escala.length - 1) {
    restante /= 1024
    passo += 1
  }
  return `${restante.toLocaleString('pt-BR', { maximumFractionDigits: passo ? 1 : 0 })} ${escala[passo]}`
}

// --- leitura de terreno ---------------------------------------------------------

/**
 * O que a imagem achou dentro do talhão.
 *
 * "Não identificado" é resposta, não desistência: o agrupamento existe e tem
 * posição medida, e só a classe é que a regra de cor não soube nomear. Chamá-lo
 * de mata por precaução tiraria área operável que talvez seja lavoura.
 */
const TERRAIN_KIND: Record<string, string> = {
  mata: 'Mata',
  carreador: 'Carreador',
  solo_exposto: 'Solo exposto',
  desconhecido: 'Não identificado',
}

export const terrainKind = (value: string | null | undefined) => lookup(TERRAIN_KIND, value)

const COVER_CLASS: Record<string, string> = {
  lavoura: 'Lavoura',
  mata: 'Mata',
  solo: 'Solo exposto',
  outro: 'Não separado',
}

export const coverClass = (value: string | null | undefined) => lookup(COVER_CLASS, value)
