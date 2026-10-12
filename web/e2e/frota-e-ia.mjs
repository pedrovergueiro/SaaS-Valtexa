// Roteiro de navegador da Parte 3: frota com estado derivado (cliente e plataforma)
// e a tela IA (registry, liberação, saúde da IA).
//
// Pré-requisitos: API servindo o build na porta 8765, num banco com o seed de
// demonstração, as contas ia@valtexa.dev (IA & Dados) e operacoes@valtexa.dev
// (Operações), e dois rovers da fazenda de demonstração que já falaram o protocolo:
// E2E-R1 com coffee-foliar 1.0.0 (o designado) e E2E-R2 com leaf-foliar e uma
// falha de câmera. Esse banco sai de e2e/prepara_frota_e_ia.py. Os rovers ficam offline
// 5 min depois da telemetria: rode o roteiro logo depois de preparar.
//
//   npm i --no-save playwright && node e2e/frota-e-ia.mjs /tmp
import { chromium } from 'playwright'
const BASE = 'http://localhost:8765'
const SHOTS = process.argv[2]
const b = await chromium.launch(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {})
const passo = (t) => console.log('✓', t)

async function entrar(email) {
  const p = await b.newPage({ viewport: { width: 1360, height: 900 } })
  p.on('pageerror', (e) => console.log('ERRO JS:', e.message))
  await p.goto(`${BASE}/entrar`)
  await p.fill('input[type=email]', email)
  await p.fill('input[type=password]', 'valtexa-demo-2026')
  await p.click('button[type=submit]')
  return p
}

// --- cliente: frota ------------------------------------------------------------
const c = await entrar('admin@valtexa.dev')
await c.getByRole('navigation', { name: 'Navegação principal' }).first().waitFor()
await c.goto(`${BASE}/frota`)
await c.getByText('E2E-R2').first().waitFor()
await c.getByText(/Falha na última telemetria: CAM_LATERAL/).first().waitFor()
await c.getByText('Modelo diferente do designado').first().waitFor()
await c.getByText('Modelo conforme').first().waitFor()
passo('frota do cliente: estado derivado com motivo e conformidade do modelo')
await c.screenshot({ path: `${SHOTS}/11-frota-cliente.png`, fullPage: true })

await c.getByText('E2E-R1').first().click()
await c.getByText('Rover Runtime').waitFor()
await c.getByText(/9,0 de 64,0 GB livres/).waitFor()
await c.getByText('212,4 h').waitFor()
passo('detalhe do robô: versões, armazenamento e horímetro informados pelo protocolo')
await c.screenshot({ path: `${SHOTS}/12-robo.png`, fullPage: true })

// --- Operações: frota de todos os clientes ---------------------------------------
const o = await entrar('operacoes@valtexa.dev')
await o.waitForURL('**/plataforma/**')
await o.goto(`${BASE}/plataforma/frota`)
await o.getByRole('cell', { name: 'Fazenda Demonstração' }).first().waitFor()
await o.getByLabel('Só com modelo diferente do designado').check()
await o.getByRole('cell', { name: /E2E-R2/ }).waitFor()
if (await o.getByRole('cell', { name: /E2E-R1/ }).count()) throw new Error('o filtro de divergentes deixou passar o conforme')
passo('Operações: frota de todos os clientes, filtro "modelo diferente do designado"')
await o.screenshot({ path: `${SHOTS}/13-frota-plataforma.png`, fullPage: true })

// --- IA & Dados: registry, liberação e saúde ---------------------------------------
const i = await entrar('ia@valtexa.dev')
await i.waitForURL('**/plataforma/**')
await i.goto(`${BASE}/plataforma/ia`)
await i.getByText('coffee-foliar').first().waitFor()
await i.getByText('aerial-canopy').first().waitFor()
passo('registry com o catálogo inicial (estados reais: aerial-canopy em treinamento)')
await i.screenshot({ path: `${SHOTS}/14-registry.png`, fullPage: true })

await i.getByRole('row', { name: /aerial-canopy/ }).getByRole('button', { name: 'Abrir' }).click()
await i.getByRole('button', { name: 'Validação' }).click()
await i.getByRole('button', { name: 'Levar para Validação' }).click()
await i.getByText(/Treinamento → Validação/).waitFor()
passo('transição Treinamento → Validação aparece no histórico com quem fez')
await i.keyboard.press('Escape')

await i.getByRole('tab', { name: 'Liberação por cliente' }).click()
await i.getByText('Liberar modelo').waitFor()
await i.getByRole('tab', { name: 'Saúde da IA' }).click()
await i.getByText('Robôs com modelo diferente').waitFor()
await i.getByText('drift').waitFor()
passo('saúde da IA: medido + "sem dado" para drift e incidentes')
await i.screenshot({ path: `${SHOTS}/15-saude-ia.png`, fullPage: true })

await b.close()
