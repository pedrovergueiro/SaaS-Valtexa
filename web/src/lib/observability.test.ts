import { describe, expect, it } from 'vitest'

import {
  alertCounts,
  alertTone,
  classShares,
  componentTone,
  deliveryLabel,
  driftTone,
  ms,
  pct,
  roverIssues,
  ruleThreshold,
  seconds,
  sortAlerts,
  usageTone,
  type RoverHealth,
} from './observability'

const robo = (over: Partial<RoverHealth> = {}): RoverHealth => ({
  device_id: 'd1',
  name: 'Rover 1',
  serial_number: 'R1',
  tenant_id: 't1',
  status: 'active',
  cpu_percent: null,
  memory_percent: null,
  accelerator_percent: null,
  accelerator_name: null,
  disk_percent: null,
  temperature_c: null,
  battery_percent: null,
  cameras_total: 0,
  cameras_ok: 0,
  cameras: [],
  sensors: {},
  connectivity: 'ok',
  last_seen_at: null,
  offline_minutes: null,
  sync_pending: 0,
  sync_oldest_pending_s: null,
  sync_blocked: false,
  last_sync_at: null,
  edge_ai: {},
  versions: {},
  faults: [],
  health_reported_at: null,
  simulated: [],
  open_alerts: 0,
  ...over,
})

describe('não medido não é zero', () => {
  it('percentual e tempo', () => {
    expect(pct(null)).toBe('não medido')
    expect(pct(0)).toBe('0%')
    expect(pct(12.34, 1)).toBe('12,3%')
    expect(ms(undefined)).toBe('não medido')
    expect(ms(4.25)).toBe('4,3 ms')
    expect(ms(1500)).toBe('1,50 s')
    expect(seconds(30)).toBe('30 s')
    expect(seconds(600)).toBe('10 min')
    expect(seconds(7200)).toBe('2,0 h')
  })

  it('tom de uso contra o limite', () => {
    expect(usageTone(null, 90)).toBe('neutral')
    expect(usageTone(50, 90)).toBe('good')
    expect(usageTone(80, 90)).toBe('warning')
    expect(usageTone(95, 90)).toBe('critical')
  })
})

describe('alertas', () => {
  const a = (state: string, severity: string, fired_at: string) => ({ state, severity, fired_at })

  it('ordem: disparado crítico, disparado aviso, reconhecido, resolvido; recente primeiro', () => {
    const lista = [
      a('resolvido', 'critico', '2026-10-05T10:00:00Z'),
      a('disparado', 'aviso', '2026-10-05T09:00:00Z'),
      a('reconhecido', 'critico', '2026-10-05T11:00:00Z'),
      a('disparado', 'critico', '2026-10-05T08:00:00Z'),
      a('disparado', 'critico', '2026-10-05T09:30:00Z'),
    ]
    expect(sortAlerts(lista).map((x) => `${x.state}/${x.severity}/${x.fired_at.slice(11, 16)}`)).toEqual([
      'disparado/critico/09:30',
      'disparado/critico/08:00',
      'disparado/aviso/09:00',
      'reconhecido/critico/11:00',
      'resolvido/critico/10:00',
    ])
    expect(alertCounts(lista)).toEqual({ open: 4, critical: 2, acknowledged: 1 })
  })

  it('tons', () => {
    expect(alertTone({ state: 'disparado', severity: 'critico' })).toBe('critical')
    expect(alertTone({ state: 'disparado', severity: 'aviso' })).toBe('warning')
    expect(alertTone({ state: 'reconhecido', severity: 'critico' })).toBe('info')
    expect(alertTone({ state: 'resolvido', severity: 'critico' })).toBe('good')
    expect(componentTone('falha')).toBe('critical')
    expect(componentTone('atencao')).toBe('warning')
    expect(deliveryLabel('nao_enviado')).toBe('não enviado(s)')
  })

  it('limite da regra por unidade', () => {
    expect(ruleThreshold({ threshold: 90, unit: '%', window_minutes: null })).toBe('90%')
    expect(ruleThreshold({ threshold: 5, unit: '%', window_minutes: 5 })).toBe('5% em 5 min')
    expect(ruleThreshold({ threshold: 30, unit: 'min', window_minutes: null })).toBe('30 min')
    expect(ruleThreshold({ threshold: 0.25, unit: 'distância', window_minutes: 1440 })).toBe('0,25 em 24,0 h')
    expect(ruleThreshold({ threshold: null, unit: null, window_minutes: null })).toBe('sem limite (qualquer ocorrência)')
  })
})

describe('saúde do robô', () => {
  it('sem problema nenhum: lista vazia', () => {
    expect(roverIssues(robo({ disk_percent: 40, temperature_c: 30 }))).toEqual([])
  })

  it('cada problema numa frase curta', () => {
    const r = robo({
      connectivity: 'offline',
      offline_minutes: 45,
      disk_percent: 95,
      temperature_c: 80,
      cameras: [
        { id: 'cam-0', ok: true },
        { id: 'cam-1', ok: false, detail: 'timeout' },
      ],
      sync_pending: 12,
      sync_oldest_pending_s: 3600,
    })
    expect(roverIssues(r)).toEqual([
      'sem comunicação há 45 min',
      'disco em 95%',
      '80,0 °C',
      'câmera cam-1 sem responder',
      '12 registro(s) esperando há 60 min',
    ])
    expect(roverIssues(robo({ sync_blocked: true, sync_pending: 3 }))).toEqual(['sincronização travada'])
  })
})

describe('IA', () => {
  it('distribuição de classes em fração, maior primeiro', () => {
    expect(classShares({ Rust: 30, Healthy: 25 })).toEqual([
      { label: 'Rust', count: 30, share: 30 / 55 },
      { label: 'Healthy', count: 25, share: 25 / 55 },
    ])
    expect(classShares({})).toEqual([])
    expect(driftTone(null)).toBe('neutral')
    expect(driftTone(0.3)).toBe('warning')
    expect(driftTone(0.1)).toBe('good')
  })
})
