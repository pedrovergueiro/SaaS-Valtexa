// Roteiro de navegador da Parte 5: resultado da missão (cliente), Atualizações (OTA) e
// rodadas de otimização dNATY (console interno).
//
// Pré-requisitos: API servindo o build na porta 8765 num banco preparado por
// e2e/prepara_resultado_e_ota.py (que grava os IDs num JSON):
//
//   npm i --no-save playwright && node e2e/resultado-e-ota.mjs /tmp/e2e5.json /tmp
import { readFileSync } from 'node:fs'
import { chromium } from 'playwright'

const BASE = 'http://localhost:8765'
const dados = JSON.parse(readFileSync(process.argv[2], 'utf8'))
const SHOTS = process.argv[3]
const b = await chromium.launch(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {})
const passo = (t) => console.log('✓', t)
let erros = 0

async function entrar(email) {
  const p = await b.newPage({ viewport: { width: 1360, height: 900 } })
  p.on('pageerror', (e) => {
    erros += 1
    console.log('ERRO JS:', e.message)
  })
  await p.goto(`${BASE}/entrar`)
  await p.fill('input[type=email]', email)
  await p.fill('input[type=password]', dados.senha)
  await p.click('button[type=submit]')
  return p
}

// --- cliente: resultado da segunda missão ------------------------------------------
const c = await entrar('gestor@pap.dev')
await c.getByRole('navigation', { name: 'Navegação principal' }).first().waitFor()
await c.goto(`${BASE}/missoes/${dados.missao2}`)
await c.getByText('Resultado da missão').waitFor()
await c.getByText(/de 54 plantas/).first().waitFor()
await c.getByText(/caiu/).first().waitFor()
await c.getByText('simulação').first().waitFor()
await c.getByText('L3-P004').first().waitFor()
passo('resultado da missão: incidência por planta, queda em relação à anterior, ocorrência, marca de simulação')
await c.getByText('Resultado da missão').scrollIntoViewIfNeeded()
await c.screenshot({ path: `${SHOTS}/51-resultado-da-missao.png`, fullPage: true })

// --- Operações: atualizações (OTA) ---------------------------------------------------
const o = await entrar('ops.e2e@equipe.valtexa.dev')
await o.waitForURL('**/plataforma/**')
await o.getByRole('link', { name: 'Atualizações (OTA)' }).first().click()
await o.getByText('cfg-e2e').first().waitFor()
await o.locator('td').getByText('Pendente').first().waitFor()
await o.getByRole('button', { name: 'Cancelar' }).first().waitFor()
passo('Atualizações (OTA): pacote, robô, estado e cancelamento para Operações')
await o.screenshot({ path: `${SHOTS}/52-ota.png`, fullPage: true })
await o.getByRole('button', { name: 'Cancelar' }).first().click()
await o.locator('td').getByText('Cancelada').first().waitFor()
passo('cancelar antes de instalar')

// --- IA & Dados: rodadas de otimização ------------------------------------------------
const i = await entrar('ia1.e2e@equipe.valtexa.dev')
await i.waitForURL('**/plataforma/**')
await i.goto(`${BASE}/plataforma/ia`)
await i.getByRole('row', { name: /9.9.9-e2e/ }).getByRole('button', { name: 'Abrir' }).click()
await i.getByText('Otimização (dNATY e outras)').waitFor()
await i.getByText('Recusada').first().waitFor()
await i.getByText('Aceita').first().waitFor()
await i.getByText(/Recall de Phoma caiu/).first().waitFor()
await i.getByText(/BSL 1.1/).first().waitFor()
passo('detalhe do modelo: rodada recusada (com o motivo) e aceita, licença BSL anotada')
await i.screenshot({ path: `${SHOTS}/53-otimizacao.png`, fullPage: true })

await b.close()
if (erros) {
  console.log(`${erros} erro(s) de JavaScript`)
  process.exit(1)
}
console.log('4 de 4 passos ok')
