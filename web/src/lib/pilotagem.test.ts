import { describe, expect, it } from 'vitest'

import {
  BOTOES,
  type ControleBruto,
  eixo,
  fonteAtiva,
  idadeDoQuadro,
  lerControle,
  proximaCamera,
  rotuloDaIdade,
  tomDaIdade,
  trocaMarcha,
} from './pilotagem'

const controle = (axes: number[], apertados: number[] = []): ControleBruto => ({
  axes,
  buttons: Array.from({ length: 17 }, (_, i) => ({ pressed: apertados.includes(i), value: apertados.includes(i) ? 1 : 0 })),
})

describe('controle de videogame', () => {
  it('zona morta sem salto e curva fina perto do centro', () => {
    expect(eixo(0.1)).toBe(0)
    expect(eixo(1)).toBe(1)
    expect(eixo(-1)).toBe(-1)
    expect(eixo(0.13)).toBeLessThan(0.01) // sai da zona morta perto de zero, sem salto
    expect(eixo(0.5)).toBeLessThan(0.5) // expo: metade do curso dá menos que metade
    expect(eixo(Number.NaN)).toBe(0)
  })

  it('acelerador no esquerdo, direção no direito, homem-morto no ombro', () => {
    const l = lerControle(controle([0, -1, 0.6, 0], [BOTOES.RB]))
    expect(l.y).toBe(1) // para cima no controle = frente
    expect(l.x).toBeGreaterThan(0)
    expect(l.homemMorto).toBe(true)
    expect(lerControle(controle([0, -1, 0, 0])).homemMorto).toBe(false)
  })

  it('botões contam na borda de subida (segurar B não repete o PARAR)', () => {
    const antes = controle([0, 0, 0, 0], [BOTOES.B])
    expect(lerControle(controle([0, 0, 0, 0], [BOTOES.B])).parar).toBe(true)
    expect(lerControle(controle([0, 0, 0, 0], [BOTOES.B]), antes).parar).toBe(false)
    expect(lerControle(controle([0, 0, 0, 0], [BOTOES.CIMA])).marchaMais).toBe(true)
    expect(lerControle(controle([0, 0, 0, 0], [BOTOES.Y])).cameraProxima).toBe(true)
  })
})

describe('quem manda', () => {
  const zero = { x: 0, y: 0 }
  it('controle só com homem-morto; depois joystick da tela; depois teclado', () => {
    const solto = lerControle(controle([0, -1, 0, 0]))
    expect(fonteAtiva({ controle: solto, joystick: zero, teclado: { x: 0, y: 1 } }).fonte).toBe('teclado')
    const seguro = lerControle(controle([0, -1, 0, 0], [BOTOES.LB]))
    expect(fonteAtiva({ controle: seguro, joystick: { x: 1, y: 0 }, teclado: zero }).fonte).toBe('controle')
    expect(fonteAtiva({ controle: null, joystick: { x: 1, y: 0 }, teclado: zero }).fonte).toBe('joystick')
    expect(fonteAtiva({ controle: null, joystick: zero, teclado: zero })).toEqual({ fonte: 'nenhuma', x: 0, y: 0 })
  })
})

describe('marcha, câmera e idade do quadro', () => {
  it('marcha em degraus, sem passar dos limites', () => {
    expect(trocaMarcha(0.5, 1)).toBe(0.75)
    expect(trocaMarcha(1, 1)).toBe(1)
    expect(trocaMarcha(0.1, -1)).toBe(0.1)
    expect(trocaMarcha(0.3, -1)).toBe(0.25)
  })

  it('câmera dá a volta', () => {
    expect(proximaCamera(['a', 'b', 'c'], 'c', 1)).toBe('a')
    expect(proximaCamera(['a', 'b', 'c'], 'a', -1)).toBe('c')
    expect(proximaCamera([], null, 1)).toBeNull()
  })

  it('idade do quadro diz quanto confiar no vídeo', () => {
    const agora = Date.parse('2026-10-10T12:00:01.000Z')
    expect(idadeDoQuadro('2026-10-10T12:00:00.600Z', agora)).toBe(400)
    expect(tomDaIdade(400)).toBe('good')
    expect(tomDaIdade(1500)).toBe('warning')
    expect(tomDaIdade(5000)).toBe('critical')
    expect(rotuloDaIdade(400)).toBe('400 ms')
    expect(rotuloDaIdade(null)).toBe('sem horário')
    expect(idadeDoQuadro(null, agora)).toBeNull()
  })
})
