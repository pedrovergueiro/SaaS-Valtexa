/**
 * Comunicação da fazenda: nuvem → base (Starlink) → rádios → Rover.
 *
 * A base manda o retrato dela (backend: services/estacao_base.py); estas funções só
 * traduzem para a tela — estado de cada rádio, o resumo de cada trecho e o que alarma.
 */

export type EnlaceRadio = {
  nome: string
  estado: 'vivo' | 'degradado' | 'morto' | null
  rtt_ms: number | null
  perda: number | null
  vazao_bps: number | null
  rssi_dbm: number | null
  snr_db: number | null
  quedas: number | null
}

export type Caminho =
  | { modo: 'direto' }
  | {
      modo: 'base'
      base: { id: string; name: string; serial_number: string; reportado_em: string | null }
      nuvem_base: { ok: boolean; quedas: number | null; contato_ha_s: number | null }
      base_rover: { vivo: boolean; melhor: string | null; em_travessia: boolean; enlaces: EnlaceRadio[] }
      uplink: Record<string, number> | null
    }

export type Tom = 'good' | 'warning' | 'critical' | 'neutral'

export function tomDoEnlace(e: Pick<EnlaceRadio, 'estado'>): Tom {
  if (e.estado === 'vivo') return 'good'
  if (e.estado === 'degradado') return 'warning'
  if (e.estado === 'morto') return 'critical'
  return 'neutral'
}

export function rotuloDoEnlace(e: Pick<EnlaceRadio, 'estado'>): string {
  const rotulos: Record<string, string> = { vivo: 'no ar', degradado: 'degradado', morto: 'sem sinal' }
  return (e.estado && rotulos[e.estado]) || 'sem medida'
}

function vazao(bps: number): string {
  if (bps >= 1e6) return `${(bps / 1e6).toLocaleString('pt-BR', { maximumFractionDigits: 1 })} Mbit/s`
  return `${Math.round(bps / 1e3).toLocaleString('pt-BR')} kbit/s`
}

/** "80 ms · 2% de perda · 900 kbit/s · −78 dBm" — só o que foi medido. */
export function resumoDoEnlace(e: EnlaceRadio): string {
  const partes: string[] = []
  if (e.rtt_ms != null) partes.push(`${Math.round(e.rtt_ms)} ms`)
  if (e.perda != null) partes.push(`${Math.round(e.perda * 100)}% de perda`)
  if (e.vazao_bps) partes.push(vazao(e.vazao_bps))
  if (e.rssi_dbm != null) partes.push(`${e.rssi_dbm} dBm`)
  if (e.snr_db != null) partes.push(`SNR ${e.snr_db} dB`)
  return partes.length ? partes.join(' · ') : 'sem medida'
}

/** Pedidos esperando a Starlink: os urgentes (P0-P3) e o lote (P4) separados. */
export function filaDoUplink(uplink: Record<string, number> | null | undefined): { urgentes: number; lote: number } {
  const u = uplink ?? {}
  return { urgentes: (u.P0 ?? 0) + (u.P1 ?? 0) + (u.P2 ?? 0) + (u.P3 ?? 0), lote: u.P4 ?? 0 }
}

export type Trecho = { nome: string; tom: Tom; detalhe: string }

/** Os dois trechos do caminho do Rover, para a faixa do centro de comando. */
export function trechos(c: Caminho): Trecho[] {
  if (c.modo === 'direto') {
    return [{ nome: 'Rover → nuvem', tom: 'neutral', detalhe: 'direto (nenhuma base o cita no último retrato)' }]
  }
  const fila = filaDoUplink(c.uplink)
  const nuvem: Trecho = {
    nome: `Nuvem ⇄ ${c.base.name}`,
    tom: c.nuvem_base.ok ? (fila.urgentes > 50 ? 'warning' : 'good') : 'critical',
    detalhe: c.nuvem_base.ok
      ? `Starlink no ar${fila.urgentes ? ` · ${fila.urgentes} urgentes na fila` : ''}${fila.lote ? ` · ${fila.lote} no lote` : ''}`
      : 'sem internet: os Rovers guardam tudo na fila deles',
  }
  const vivos = c.base_rover.enlaces.filter((e) => e.estado && e.estado !== 'morto')
  const radio: Trecho = {
    nome: `${c.base.name} ⇄ Rover`,
    tom: !c.base_rover.vivo ? (c.base_rover.em_travessia ? 'warning' : 'critical') : vivos.some((e) => e.estado === 'vivo') ? 'good' : 'warning',
    detalhe: !c.base_rover.vivo
      ? c.base_rover.em_travessia
        ? 'em zona morta mapeada: sincroniza na volta'
        : 'sem nenhum rádio'
      : `${vivos.length} de ${c.base_rover.enlaces.length} rádio(s) no ar${c.base_rover.melhor ? ` · lote pelo ${c.base_rover.melhor}` : ''}`,
  }
  return [nuvem, radio]
}
