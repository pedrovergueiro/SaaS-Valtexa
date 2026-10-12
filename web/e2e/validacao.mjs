// Roteiro de navegador da aba Validação do Rover (Parte 11, rodada 3).
//
// Pré-requisitos: `npm run build`, banco preparado por `web/e2e/prepara_validacao.py`
// (que imprime o id do rover) e uvicorn servindo o build na porta 8765:
//
//   npm i --no-save playwright && node e2e/validacao.mjs <rover_id> /tmp
//
// Confere: o centro de comando leva à Validação; o portão real da FASE 0 está fechado
// com os ensaios "só simulado"; os resultados mostram o veredito do servidor com a marca
// de simulado; um limite frouxo desliga o botão; um ensaio novo entra em curso e o
// cancelamento o tira da fila.
import { chromium } from 'playwright'
const BASE = 'http://localhost:8765'
const [ROVER, SHOTS] = process.argv.slice(2)
const b = await chromium.launch({ executablePath: process.env.CHROMIUM || undefined })
const p = await b.newPage({ viewport: { width: 1360, height: 900 } })
const passo = (t) => console.log('✓', t)
const erros = []
p.on('pageerror', (e) => { erros.push(e.message); console.log('ERRO JS:', e.message) })

await p.goto(`${BASE}/entrar`)
await p.fill('input[type=email]', 'chefe@valtexa.dev')
await p.fill('input[type=password]', 'valtexa-demo-2026')
await p.click('button[type=submit]')
await p.waitForURL('**/plataforma/**')
await p.goto(`${BASE}/plataforma/comando/${ROVER}`)
await p.getByRole('link', { name: 'Validação' }).click()
await p.waitForURL(`**/plataforma/comando/${ROVER}/validacao`)
passo('o centro de comando leva à aba Validação')

await p.getByText('Bancada, sem andar').waitFor()
await p.getByText('Portão fechado').first().waitFor()
const soSimulado = await p.getByText('Só simulado').count()
if (soSimulado < 8) throw new Error(`esperava 8+ "Só simulado", vi ${soSimulado}`)
passo(`portão real da FASE 0 fechado; ${soSimulado} itens "só simulado"`)
await p.getByText('Manual (guia)').first().waitFor()
passo('fases sem ensaio automático aparecem como manuais')
await p.screenshot({ path: `${SHOTS}/v1-portoes.png`, fullPage: true })

const linhas = await p.locator('tbody tr').count()
if (linhas < 9) throw new Error(`esperava 9 resultados, vi ${linhas}`)
const simulados = await p.locator('tbody').getByText('simulado', { exact: true }).count()
if (simulados < 9) throw new Error(`resultados sem a marca de simulado: ${simulados}`)
await p.locator('tbody tr', { hasText: 'imu · fase' }).first().click()
await p.getByText(/✓ .*:/).first().waitFor()
passo(`${linhas} resultados com veredito do servidor, todos marcados simulado; critérios abrem no clique`)

await p.selectOption('select[aria-label="Ensaio"]', 'rede')
await p.getByLabel(/perda_max_pct/).fill('50')
await p.getByText('Mais frouxo que o portão').waitFor()
if (!(await p.getByRole('button', { name: 'Rodar rede' }).isDisabled())) throw new Error('limite frouxo não desligou o botão')
passo('limite frouxo: a tela avisa e não deixa mandar')
await p.getByLabel(/perda_max_pct/).fill('1')
await p.getByRole('button', { name: 'Rodar rede' }).click()
await p.getByText('Ensaio enviado').waitFor()
await p.getByRole('button', { name: 'Cancelar' }).waitFor()
passo('ensaio novo assinado e na fila "Em curso"')
await p.screenshot({ path: `${SHOTS}/v2-em-curso.png`, fullPage: true })
await p.getByRole('button', { name: 'Cancelar' }).click()
await p.getByText('Nenhum ensaio rodando').waitFor()
passo('cancelado na fila (ainda não entregue ao rover)')
if (erros.length) throw new Error('erros de JavaScript: ' + erros.join(' | '))
await b.close()
