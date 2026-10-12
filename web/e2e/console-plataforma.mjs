// Roteiro de navegador do console da plataforma (Fase 3).
//
// Pré-requisitos: API servindo o build (`npm run build` e uvicorn na porta 8765) num
// banco com o seed de demonstração mais as contas `suporte@valtexa.dev` (papel
// suporte, sem associação) e `admin@valtexa.dev`. Rodar com o Playwright instalado
// à parte (não é dependência do console):
//
//   npm i --no-save playwright && node e2e/console-plataforma.mjs /tmp
//
// Confere: equipe cai em /plataforma; entrar como cliente exige motivo; a faixa
// aparece em toda tela do cliente; sair volta à plataforma; a entrada aparece na
// auditoria global; o console do cliente não mostra item de plataforma.
import { chromium } from 'playwright'
const BASE = 'http://localhost:8765'
const SHOTS = process.argv[2]
const b = await chromium.launch()
const p = await b.newPage({ viewport: { width: 1360, height: 860 } })
const passo = (t) => console.log('✓', t)
p.on('pageerror', (e) => console.log('ERRO JS:', e.message))

await p.goto(`${BASE}/entrar`)
await p.fill('input[type=email]', 'suporte@valtexa.dev')
await p.fill('input[type=password]', 'valtexa-demo-2026')
await p.click('button[type=submit]')
await p.waitForURL('**/plataforma/clientes')
passo('suporte cai no console da plataforma, não no do cliente')
await p.getByText('Fazenda Demonstração').waitFor()
await p.getByText('Console da plataforma').first().waitFor()
await p.screenshot({ path: `${SHOTS}/1-clientes.png` })
const menu = await p.locator('nav[aria-label="Console da plataforma"] a').allInnerTexts()
console.log('  menu:', menu.join(' | '))

await p.getByRole('button', { name: 'Entrar como cliente' }).first().click()
const entrar = p.getByRole('button', { name: 'Entrar em modo leitura' })
if (!(await entrar.isDisabled())) throw new Error('entrou sem motivo')
passo('sem motivo o botão fica desligado')
await p.fill('textarea', 'Chamado 42: o talhão sumiu do mapa')
await p.screenshot({ path: `${SHOTS}/2-entrar.png` })
await entrar.click()
await p.waitForURL(`${BASE}/`)
await p.getByText('Suporte ValTexa em Fazenda Demonstração').waitFor()
await p.getByText('Modo leitura').waitFor()
passo('dentro do cliente, com a faixa no topo')
await p.waitForTimeout(1500)
await p.screenshot({ path: `${SHOTS}/3-dentro.png` })

await p.goto(`${BASE}/talhoes`)
await p.getByText('Suporte ValTexa em').waitFor()
passo('a faixa continua em outra tela')

await p.getByRole('button', { name: 'Sair do cliente' }).click()
await p.waitForURL('**/plataforma/clientes**')
passo('saiu e voltou ao console da plataforma')

await p.goto(`${BASE}/plataforma/auditoria`)
await p.getByRole('tab', { name: 'Entradas em clientes' }).click()
await p.getByText('Chamado 42').first().waitFor()
await p.screenshot({ path: `${SHOTS}/4-auditoria.png` })
passo('a entrada aparece na auditoria global')

await p.goto(`${BASE}/plataforma/usuarios`)
await p.getByText('agronomo@valtexa.dev').waitFor()
passo('usuários globais listados')
await p.screenshot({ path: `${SHOTS}/5-usuarios.png` })

// cliente comum: sem item de plataforma no menu e sem acesso a /plataforma
const c = await b.newPage({ viewport: { width: 1360, height: 860 } })
await c.goto(`${BASE}/entrar`)
await c.fill('input[type=email]', 'admin@valtexa.dev')
await c.fill('input[type=password]', 'valtexa-demo-2026')
await c.click('button[type=submit]')
await c.getByRole('navigation', { name: 'Navegação principal' }).first().waitFor()
const itens = await c.locator('nav[aria-label="Navegação principal"] a').allInnerTexts()
if (itens.some((t) => /Clientes|Importar coleta|Dataset/.test(t))) throw new Error('item de plataforma no cliente: ' + itens)
passo('console do cliente sem itens de plataforma: ' + itens.join(', '))
await c.goto(`${BASE}/plataforma/clientes`)
await c.waitForURL(`${BASE}/`)
passo('cliente que tenta /plataforma volta ao próprio console')
await b.close()
