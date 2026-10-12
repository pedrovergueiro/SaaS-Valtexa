// Roteiro de navegador da Parte 7: observabilidade no console do cliente (saúde da
// frota, alertas, reconhecer, regra própria) e no da plataforma (componentes, API,
// robôs, IA, alertas, regras).
//
// Pré-requisitos: API servindo o build na porta 8765 num banco preparado por
// e2e/prepara_observabilidade.py:
//
//   npm i --no-save playwright && node e2e/observabilidade.mjs /tmp/e2e7.json /tmp
import { readFileSync } from 'node:fs'
import { chromium } from 'playwright'

const BASE = 'http://localhost:8765'
const dados = JSON.parse(readFileSync(process.argv[2], 'utf8'))
const SHOTS = process.argv[3]
const b = await chromium.launch(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {})
let passos = 0
const passo = (t) => {
  passos += 1
  console.log('✓', t)
}
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

// --- gestor do cliente -----------------------------------------------------------------
const g = await entrar('admin@valtexa.dev')
await g.getByRole('navigation', { name: 'Navegação principal' }).first().waitFor()
await g.getByRole('link', { name: 'Saúde da frota' }).first().click()
await g.getByText('E2E-DISCO-CHEIO').first().waitFor()
await g.getByText('disco em 96%').first().waitFor()
await g.getByText('câmera cam-1 sem responder').first().waitFor()
await g.getByText('simulado: camera, sensores, sistema').first().waitFor()
passo('cliente: saúde dos dois robôs dele, com disco cheio, câmera fora e a simulação dita')
await g.screenshot({ path: `${SHOTS}/71-saude-da-frota.png`, fullPage: true })

await g.getByRole('tab', { name: /Alertas/ }).click()
await g.getByText(/Disco do robô cheio: .*E2E-DISCO-CHEIO/).waitFor()
await g.getByText(/Câmera sem responder: .*E2E-DISCO-CHEIO/).waitFor()
passo('cliente: os alertas disparados dos robôs dele')
const linha = g.getByRole('row', { name: /Disco do robô cheio/ })
await linha.getByRole('button', { name: 'Reconhecer' }).click()
await g.getByRole('dialog').getByLabel('Nota (opcional)').fill('Técnico esvazia hoje à tarde.')
await g.getByRole('dialog').getByRole('button', { name: 'Reconhecer' }).click()
await g.getByRole('row', { name: /Disco do robô cheio/ }).getByText('Reconhecido').waitFor()
await g.getByText('“Técnico esvazia hoje à tarde.”').waitFor()
passo('cliente: reconhece o alerta de disco com uma nota')
await g.screenshot({ path: `${SHOTS}/72-alertas-cliente.png`, fullPage: true })

await g.getByRole('tab', { name: 'Regras' }).click()
await g.getByRole('row', { name: /Disco do robô cheio/ }).getByRole('button', { name: 'Ajustar' }).click()
await g.getByRole('dialog').getByLabel('Limite (%)').fill('98')
await g.getByRole('dialog').getByRole('button', { name: 'Salvar' }).click()
await g.getByRole('row', { name: /Disco do robô cheio/ }).getByText('própria deste cliente').waitFor()
await g.getByRole('row', { name: /Disco do robô cheio/ }).getByText('98%').waitFor()
if (await g.getByText('Taxa de erro da API').count()) throw new Error('cliente vê regra da plataforma')
passo('cliente: regra própria (disco a 98 %), sem ver as regras da plataforma')
await g.screenshot({ path: `${SHOTS}/73-regras-cliente.png`, fullPage: true })

// --- Operações na plataforma -------------------------------------------------------------
const o = await entrar('operacoes.e2e@equipe.valtexa.dev')
await o.waitForURL('**/plataforma/**')
await o.getByRole('link', { name: 'Observabilidade' }).click()
for (const c of ['Banco de dados', 'API', 'Worker e eventos', 'Serviço de IA', 'Frota', 'Alertas']) {
  await o.locator('[data-componente]').getByText(c, { exact: true }).first().waitFor()
}
passo('plataforma: semáforo por componente (banco, API, worker, IA, frota, alertas)')
await o.screenshot({ path: `${SHOTS}/74-plataforma-geral.png`, fullPage: true })

await o.getByRole('tab', { name: 'API' }).click()
await o.getByText('/v1/platform/observability').first().waitFor()
passo('plataforma: API por rota (molde), com p50/p95')
await o.screenshot({ path: `${SHOTS}/75-plataforma-api.png`, fullPage: true })

await o.getByRole('tab', { name: 'Robôs' }).click()
await o.getByText('E2E-SAUDAVEL').first().waitFor()
await o.getByText(/CPU 87%/).first().waitFor()
passo('plataforma: saúde dos robôs de todos os clientes')

await o.getByRole('tab', { name: 'IA' }).click()
await o.getByText('Drift da distribuição de classes').waitFor()
passo('plataforma: IA por modelo e drift (com a nota do que não é medido)')

await o.getByRole('tab', { name: /Alertas/ }).click()
await o.getByText(/Câmera sem responder: .*E2E-DISCO-CHEIO/).waitFor()
const cam = o.getByRole('row', { name: /Câmera sem responder/ })
await cam.getByRole('button', { name: 'Reconhecer' }).click()
await o.getByRole('dialog').getByRole('button', { name: 'Reconhecer' }).click()
await o.getByRole('row', { name: /Câmera sem responder/ }).getByText('(equipe ValTexa)').waitFor()
passo('plataforma: alertas de todos os clientes; Operações reconhece o da câmera')
await o.screenshot({ path: `${SHOTS}/76-plataforma-alertas.png`, fullPage: true })

await o.getByRole('tab', { name: 'Regras' }).click()
await o.getByText('Drift da distribuição de classes').first().waitFor()
await o.getByText('Taxa de erro da API').waitFor()
passo('plataforma: as 10 regras padrão, editáveis por Operações')

await b.close()
console.log(`\n${passos} de 10 passos, ${erros} erro(s) de JS`)
if (passos !== 10 || erros) process.exit(1)
