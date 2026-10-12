// Roteiro de navegador da Parte 6: notificações (sino, central, preferências) e suporte
// (chamado do cliente, atendimento pela equipe, nota interna, entrar como cliente pelo chamado).
//
// Pré-requisitos: API servindo o build na porta 8765 (com o worker na API) num banco
// preparado por e2e/prepara_suporte_e_avisos.py:
//
//   npm i --no-save playwright && node e2e/suporte-e-avisos.mjs /tmp/e2e6.json /tmp
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

// --- operador: sino, central e o e-mail "não enviado" -------------------------------
const op = await entrar('operador@valtexa.dev')
await op.getByRole('navigation', { name: 'Navegação principal' }).first().waitFor()
const sino = op.getByRole('button', { name: /Notificações: 1 não lidas/ })
await sino.waitFor()
await sino.click()
await op.getByText(/E2E-ROVER-6.*sem comunicação/).first().waitFor()
passo('sino com 1 não lida e o aviso "robô sem comunicação" (gerado pelo worker a partir do evento)')
await op.screenshot({ path: `${SHOTS}/61-sino.png` })
await op.getByRole('link', { name: 'Abrir a central e as preferências' }).click()
await op.getByText(/E-mail: não enviado — SMTP não configurado/).first().waitFor()
passo('central: a entrega por e-mail aparece como "não enviado", com o motivo (sem SMTP)')
await op.screenshot({ path: `${SHOTS}/62-central.png`, fullPage: true })

await op.getByRole('tab', { name: 'Minhas preferências' }).click()
await op.getByText('O envio por e-mail ainda não está configurado').waitFor()
await op.getByRole('checkbox', { name: 'E-mail: Robô sem comunicação' }).uncheck()
await op.getByRole('row', { name: /Robô sem comunicação/ }).getByRole('button', { name: 'Salvar' }).click()
await op.getByRole('row', { name: /Robô sem comunicação/ }).getByText('sua escolha').waitFor()
passo('preferências: tirar o e-mail de "robô sem comunicação" e ver a origem "sua escolha"')
await op.screenshot({ path: `${SHOTS}/63-preferencias.png`, fullPage: true })

// --- operador abre um chamado ligado ao robô ------------------------------------------
await op.goto(`${BASE}/suporte`)
await op.getByRole('button', { name: 'Abrir chamado' }).first().click()
const modal = op.getByRole('dialog')
await modal.getByLabel('Título').fill('Rover sem comunicação desde a manhã')
await modal.getByLabel('O que aconteceu').fill('O E2E-ROVER-6 parou de falar com a plataforma às 8h.')
await modal.getByLabel('Prioridade').selectOption('alta')
await modal.getByLabel('Robô (opcional)').selectOption(dados.device_id)
await modal.getByRole('button', { name: 'Abrir chamado' }).click()
await op.waitForURL('**/suporte/*')
await op.getByText('abriu o chamado').waitFor()
const urlChamado = op.url()
const chamadoId = urlChamado.split('/').pop()
passo('chamado aberto pelo cliente, ligado ao robô, com histórico')

// --- Suporte: aviso de chamado novo, atendimento, nota interna e resposta -------------
const sup = await entrar('suporte.e2e@equipe.valtexa.dev')
await sup.waitForURL('**/plataforma/**')
// O worker da API entrega o evento em até ~5 s; o sino consulta a cada 30 s.
let avisado = false
for (let i = 0; i < 12 && !avisado; i += 1) {
  await sup.goto(`${BASE}/plataforma/notificacoes`)
  avisado = await sup
    .getByText(/CH-\d+ \(alta\): Rover sem comunicação/)
    .first()
    .waitFor({ timeout: 2500 })
    .then(() => true)
    .catch(() => false)
}
if (!avisado) throw new Error('o Suporte não recebeu o aviso de chamado novo')
passo('Suporte recebe o aviso "chamado novo" na central da plataforma')

await sup.getByRole('link', { name: 'Suporte' }).first().click()
await sup.getByRole('link', { name: /Rover sem comunicação desde a manhã/ }).click()
await sup.getByLabel('Responsável').selectOption({ label: 'Sofia do Suporte' })
await sup.getByText('Em atendimento').first().waitFor()
await sup.getByLabel('Comentário').fill('Certificado do rover venceu ontem (interno).')
await sup.getByRole('checkbox', { name: /Nota interna/ }).check()
await sup.getByRole('button', { name: 'Salvar nota' }).click()
await sup.getByText('nota interna', { exact: true }).first().waitFor()
await sup.getByLabel('Comentário').fill('Estamos verificando. Pode reiniciar o rover?')
await sup.getByRole('button', { name: 'Enviar' }).click()
await sup.getByText('Estamos verificando. Pode reiniciar o rover?').waitFor()
passo('equipe assume, escreve nota interna e responde ao cliente')
await sup.screenshot({ path: `${SHOTS}/64-chamado-equipe.png`, fullPage: true })

// --- o cliente vê a resposta e não vê a nota interna ----------------------------------
await op.goto(urlChamado)
await op.getByText('Estamos verificando. Pode reiniciar o rover?').waitFor()
if (await op.getByText(/Certificado do rover venceu/).count()) throw new Error('nota interna vazou para o cliente')
passo('cliente vê a resposta da equipe e não vê a nota interna')
await op.screenshot({ path: `${SHOTS}/65-chamado-cliente.png`, fullPage: true })

// --- Suporte entra no cliente pelo chamado --------------------------------------------
await sup.goto(`${BASE}/plataforma/suporte/${chamadoId}`)
await sup.getByRole('button', { name: 'Entrar como cliente' }).click()
await sup.getByRole('dialog').getByRole('button', { name: 'Entrar em modo leitura' }).click()
await sup.waitForURL(`${BASE}/`)
await sup.goto(`${BASE}/suporte/${chamadoId}`)
await sup.getByText(/entrou na conta \(sessão de suporte\)/).first().waitFor()
passo('Suporte entra como cliente referenciando o chamado; o histórico do chamado mostra a entrada')
await sup.screenshot({ path: `${SHOTS}/66-sessao-pelo-chamado.png`, fullPage: true })

await b.close()
if (erros) {
  console.log(`${erros} erro(s) de JavaScript`)
  process.exit(1)
}
console.log(`${passos} de 8 passos ok`)
