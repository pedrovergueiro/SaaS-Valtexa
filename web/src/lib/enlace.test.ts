import { describe, expect, it } from 'vitest'

import { type Caminho, type EnlaceRadio, filaDoUplink, resumoDoEnlace, tomDoEnlace, trechos } from './enlace'

const radio = (nome: string, estado: EnlaceRadio['estado'], extra: Partial<EnlaceRadio> = {}): EnlaceRadio => ({
  nome,
  estado,
  rtt_ms: null,
  perda: null,
  vazao_bps: null,
  rssi_dbm: null,
  snr_db: null,
  quedas: null,
  ...extra,
})

const pelaBase = (over: Partial<Extract<Caminho, { modo: 'base' }>> = {}): Caminho => ({
  modo: 'base',
  base: { id: 'b1', name: 'base-sede', serial_number: 'BASE-01', reportado_em: null },
  nuvem_base: { ok: true, quedas: 0, contato_ha_s: 3 },
  base_rover: { vivo: true, melhor: 'subghz', em_travessia: false, enlaces: [radio('subghz', 'vivo'), radio('wifi5', 'morto')] },
  uplink: { P0: 0, P1: 1, P2: 3, P3: 0, P4: 40 },
  ...over,
})

describe('enlace da fazenda', () => {
  it('resumo só com o que foi medido', () => {
    expect(resumoDoEnlace(radio('x', 'vivo', { rtt_ms: 80.4, perda: 0.02, vazao_bps: 900_000, rssi_dbm: -78 }))).toBe(
      '80 ms · 2% de perda · 900 kbit/s · -78 dBm',
    )
    expect(resumoDoEnlace(radio('x', null))).toBe('sem medida')
    expect(tomDoEnlace({ estado: 'degradado' })).toBe('warning')
  })

  it('fila: urgentes separados do lote', () => {
    expect(filaDoUplink({ P1: 2, P3: 1, P4: 900 })).toEqual({ urgentes: 3, lote: 900 })
    expect(filaDoUplink(null)).toEqual({ urgentes: 0, lote: 0 })
  })

  it('os dois trechos do caminho', () => {
    const [nuvem, radioT] = trechos(pelaBase())
    expect(nuvem!.tom).toBe('good')
    expect(nuvem!.detalhe).toContain('4 urgentes na fila')
    expect(radioT!.detalhe).toBe('1 de 2 rádio(s) no ar · lote pelo subghz')
    expect(trechos({ modo: 'direto' })).toHaveLength(1)
  })

  it('sem internet e sem rádio viram perigo; zona morta mapeada é aviso', () => {
    const [nuvem] = trechos(pelaBase({ nuvem_base: { ok: false, quedas: 3, contato_ha_s: 600 } }))
    expect(nuvem!.tom).toBe('critical')
    const semRadio = trechos(pelaBase({ base_rover: { vivo: false, melhor: null, em_travessia: false, enlaces: [] } }))
    expect(semRadio[1]!.tom).toBe('critical')
    const travessia = trechos(pelaBase({ base_rover: { vivo: false, melhor: null, em_travessia: true, enlaces: [] } }))
    expect(travessia[1]!.tom).toBe('warning')
  })
})
