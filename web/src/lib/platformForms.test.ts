import { describe, expect, it } from 'vitest'

import {
  canOptimize,
  dnatyBody,
  otaDeploymentBody,
  otaPublishErrors,
  otaPublishQuery,
  otaTargetErrors,
  parseDnatyReport,
  publishableVersions,
  robotArtifact,
} from './platformForms'

const v = (state: string, orig: string | null, opt: string | null) => ({
  id: state,
  model_key: 'banana',
  version: '1',
  state,
  original_artifact_sha256: orig,
  optimized_artifact_sha256: opt,
})

describe('publicar pacote OTA', () => {
  it('só versão em PRODUÇÃO com artefato; o otimizado vai ao robô', () => {
    expect(publishableVersions([v('producao', 'aa', null), v('staging', 'bb', null), v('producao', null, null)]).map((x) => x.id)).toEqual(['producao'])
    expect(robotArtifact(v('producao', 'aa', 'bb'))).toEqual({ sha256: 'bb', kind: 'otimizado', file: 'bb.onnx' })
    expect(robotArtifact(v('producao', 'aa', null))?.file).toBe('aa.onnx')
  })

  it('o que falta antes de mandar', () => {
    const base = { kind: 'config' as const, version: 'cfg-1', modelVersionId: '', notes: '', file: { name: 'p.tar', size: 10 } }
    expect(otaPublishErrors(base)).toEqual([])
    expect(otaPublishErrors({ ...base, kind: 'model' })).toEqual(['Pacote de modelo precisa da versão do registry (em PRODUÇÃO).'])
    expect(otaPublishErrors({ ...base, file: { name: 'p.zip', size: 10 } })).toEqual(['O pacote é um arquivo .tar.'])
    expect(otaPublishErrors({ ...base, kind: '', version: ' ', file: null })).toHaveLength(3)
  })

  it('consulta e destino', () => {
    expect(otaPublishQuery({ kind: 'model', version: ' m-1 ', modelVersionId: 'mv', notes: ' nota ', file: null })).toEqual({
      kind: 'model',
      version: 'm-1',
      model_version_id: 'mv',
      notes: 'nota',
    })
    expect(otaPublishQuery({ kind: 'config', version: 'c', modelVersionId: 'mv', notes: '', file: null })).toEqual({ kind: 'config', version: 'c' })
    expect(otaDeploymentBody('p', { mode: 'cliente', tenantId: 't' })).toEqual({ package_id: 'p', tenant_id: 't' })
    expect(otaDeploymentBody('p', { mode: 'robos', deviceIds: ['a'] })).toEqual({ package_id: 'p', device_ids: ['a'] })
    expect(otaTargetErrors({ mode: 'robos', deviceIds: [] })).toEqual(['Escolha ao menos um robô.'])
    expect(otaTargetErrors({ mode: 'cliente', tenantId: '' })).toEqual(['Escolha o cliente.'])
  })
})

describe('registrar rodada dNATY', () => {
  const bench = (sha: string) => ({ precision: 0.9, recall: 0.9, f1: 0.9, latency_ms_p50: 3, size_bytes: 100, sha256: sha })
  const relatorio = {
    tool: 'dnaty',
    tool_version: '2.2.1',
    dnaty_version: '2.2.1',
    parametros: { bits: 8 },
    aceito: true,
    original: { path: '/treino/m.onnx', benchmark: bench('aa') },
    otimizado: { path: '/treino/m.otimizado.onnx', benchmark: bench('bb') },
  }

  it('lê o relatório do pipeline e pede a URI do otimizado', () => {
    const p = parseDnatyReport(JSON.stringify(relatorio))
    expect(p.ok).toBe(true)
    expect(p.paths.otimizado).toBe('/treino/m.otimizado.onnx')
    expect(p.reportVerdict).toBe(true)
    expect(p.body?.otimizado.artifact_uri).toBeNull()
    const corpo = dnatyBody(p, { original: '', otimizado: ' s3://modelos/m.otimizado.onnx ' })
    expect(corpo?.otimizado.artifact_uri).toBe('s3://modelos/m.otimizado.onnx')
    expect(corpo?.original.artifact_uri).toBeNull()
    expect(corpo?.parametros).toEqual({ bits: 8 })
  })

  it('recusa antes de mandar o que o registry recusaria', () => {
    expect(parseDnatyReport('não é json').errors).toEqual(['O arquivo não é JSON válido.'])
    expect(parseDnatyReport('[]').errors).toEqual(['O arquivo não é um objeto JSON.'])
    const semF1 = { ...relatorio, otimizado: { benchmark: { ...bench('bb'), f1: null } } }
    expect(parseDnatyReport(JSON.stringify(semF1)).errors).toEqual(['Benchmark do otimizado sem f1.'])
    const igual = { ...relatorio, otimizado: { benchmark: bench('aa') } }
    expect(parseDnatyReport(JSON.stringify(igual)).errors).toEqual(['Otimizado e original são o mesmo arquivo (mesmo SHA-256).'])
    expect(canOptimize('validacao')).toBe(true)
    expect(canOptimize('producao')).toBe(false)
  })
})
