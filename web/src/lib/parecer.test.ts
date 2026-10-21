import { describe, expect, it } from 'vitest'

import { alvoDaCitacao, avisoDeHoje, decisaoTexto, modoTexto, porSecao, seloDaFonte, situacaoTexto, situacaoTom, type FonteCitada } from './parecer'

const fonte = (extra: Partial<FonteCitada> = {}): FonteCitada => ({
  id: 'F1', documento_id: 'd', titulo: 'Bula EXEMPLO', versao: '1', tipo: 'bula', origem: 'teste', licenca: 'teste',
  secao: null, texto: 'x', sha256_trecho: 'h', uso_operacional: false, bloqueio: 'não verificado na versão vigente',
  ficticio: false, regulatorio: true, ...extra,
})

describe('parecer do cérebro agronômico', () => {
  it('agrupa as afirmações por seção, na ordem do compositor', () => {
    const g = porSecao([
      { id: 'A1', secao: 'caso', texto: 'a', citacoes: ['E1'] },
      { id: 'A2', secao: 'hipoteses', texto: 'b', citacoes: ['E2'] },
      { id: 'A3', secao: 'caso', texto: 'c', citacoes: ['E1'] },
    ])
    expect(g.map((x) => [x.titulo, x.itens.length])).toEqual([['Caso', 2], ['Hipóteses', 1]])
  })

  it('nenhuma verificação aparece como resolvida', () => {
    expect(situacaoTexto('a_verificar')).toBe('A verificar pelo responsável')
    expect(situacaoTom('bloqueado')).toBe('critical')
    expect(situacaoTexto('sem_fonte')).toBe('Sem fonte')
  })

  it('cita o item do dossiê ou o trecho da fonte, e acusa o que não existe', () => {
    const p = { dossie: { itens: [{ id: 'E1', tipo: 'caso', titulo: 'Identificação do caso', disponivel: true, motivo_indisponivel: null, origem: {}, versao_modelo: null, dados: {}, limitacoes: [] }], hipoteses: { principal: null, alternativas: [] } }, fontes: [fonte()] }
    expect(alvoDaCitacao(p, 'E1')).toBe('E1 · Identificação do caso')
    expect(alvoDaCitacao(p, 'F1')).toBe('F1 · Bula EXEMPLO v1')
    expect(alvoDaCitacao(p, 'E9')).toContain('não está no dossiê')
  })

  it('selo da fonte: fictícia e bloqueada antes de tudo', () => {
    expect(seloDaFonte(fonte({ ficticio: true, uso_operacional: true })).texto).toBe('Fictícia (teste)')
    expect(seloDaFonte(fonte()).texto).toBe('Bloqueada: não verificado na versão vigente')
    expect(seloDaFonte(fonte({ uso_operacional: true, bloqueio: null })).tom).toBe('good')
    expect(seloDaFonte(fonte({ regulatorio: false, tipo: 'embrapa' })).texto).toContain('Técnica')
  })

  it('modo e decisão em português', () => {
    expect(modoTexto({ modo: 'deterministico', provedor: null })).toBe('Compositor determinístico')
    expect(modoTexto({ modo: 'provedor', provedor: 'x' })).toBe('Texto do provedor x, validado')
    expect(decisaoTexto('inconclusivo')).toBe('Pede mais evidência')
  })

  it('avisa quando a fonte mudou depois do parecer', () => {
    const base = { id: 'F1', documento_id: 'd', existe: true, estado: 'vigente', uso_operacional: false, bloqueio: 'vencido em 2026-10-18', mudou: true }
    expect(avisoDeHoje(base)).toBe('Hoje: vencido em 2026-10-18')
    expect(avisoDeHoje({ ...base, estado: 'substituido' })).toBe('Hoje: substituido por versão mais nova')
    expect(avisoDeHoje({ ...base, existe: false })).toBe('Hoje: fora do repositório')
    expect(avisoDeHoje({ ...base, mudou: false })).toBeNull()
    expect(avisoDeHoje(undefined)).toBeNull()
  })
})
