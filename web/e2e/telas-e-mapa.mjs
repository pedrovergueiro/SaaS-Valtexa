// Roteiro de navegador da Parte 8: telas que antes só existiam na API e o mapa por camadas.
//
// Cliente: painel (seção 45), relatório da missão com registros da Edge AI (filtro por
// categoria, imagem original, CSV), comparação entre missões, linha do tempo do talhão e
// mapa por missão (camadas, calor, comparação; umidade/falhas/produtividade sem dado).
// Plataforma: publicar e destinar pacote OTA; registrar rodada dNATY.
//
// Pré-requisitos: API servindo o build na porta 8765 num banco preparado por
// e2e/prepara_telas_e_mapa.py:
//
//   npm i --no-save playwright && node e2e/telas-e-mapa.mjs /tmp/e2e8.json /tmp
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
  const ctx = await b.newContext({ viewport: { width: 1360, height: 900 }, acceptDownloads: true })
  const p = await ctx.newPage()
  p.on('pageerror', (e) => {
    erros += 1
    console.log('ERRO JS:', e.message)
  })
  // Sem internet aqui: os tiles do mapa falham, o que não é erro de JS da página.
  await p.route(/arcgisonline|openstreetmap/, (r) => r.abort())
  await p.goto(`${BASE}/entrar`)
  await p.fill('input[type=email]', email)
  await p.fill('input[type=password]', dados.senha)
  await p.click('button[type=submit]')
  return p
}

// --- cliente ------------------------------------------------------------------------------
const g = await entrar('gestor@pap.dev')
await g.getByRole('navigation', { name: 'Navegação principal' }).first().waitFor()
const visao = g.locator('[data-painel-visao]')
await visao.getByText('Área').waitFor()
await visao.getByText(/1 fazenda\(s\) · 1 talhão/).waitFor()
await visao.getByText('Ocorrências · 7 dias').waitFor()
await g.getByText('Sincronização').first().waitFor()
await g.getByRole('row', { name: /Rover Scout/ }).getByText(/há|agora/).first().waitFor()
await g.getByText('IA de nuvem simulada').waitFor()
passo('painel: área, varreduras, ocorrências, IA 24 h, saúde da frota e sincronização por robô (dados reais)')
await g.screenshot({ path: `${SHOTS}/81-painel.png`, fullPage: true })

await g.goto(`${BASE}/missoes/${dados.missao2}`)
await g.getByRole('link', { name: 'Relatório completo' }).click()
await g.waitForURL(`**/missoes/${dados.missao2}/relatorio`)
await g.getByText('Registros da Edge AI').waitFor()
// "0 registro(s)" aparece enquanto carrega: espera a contagem real (Parte 9).
await g.getByText(/[1-9]\d* registro\(s\) sincronizado\(s\)/).waitFor()
await g.getByRole('tab', { name: /Todas \(54\)/ }).waitFor()
passo('relatório da missão: resumo, plantas (54) e registros da Edge AI')

const total = await g.locator('table').last().locator('tbody tr').count()
await g.getByLabel('Categoria').selectOption('eventos')
await g.getByText(/^\d+ no filtro$/).waitFor()
const eventos = await g.locator('table').last().locator('tbody tr').count()
if (!(eventos > 0 && eventos < total)) throw new Error(`filtro por categoria: ${eventos} de ${total}`)
passo(`registros: filtro por categoria (${eventos} eventos de ${total} na primeira página)`)

await g.getByLabel('Só com imagem').check()
await g.getByRole('button', { name: 'Original' }).first().click()
const img = g.getByRole('dialog').locator('img')
await img.waitFor()
await g.waitForFunction(() => {
  const i = document.querySelector('[role=dialog] img')
  return i && i.complete && i.naturalWidth > 0
})
passo('registro: a imagem original abre, servida pela API no escopo do cliente')
await g.screenshot({ path: `${SHOTS}/82-registro-original.png` })
await g.keyboard.press('Escape')

const [download] = await Promise.all([g.waitForEvent('download'), g.getByRole('button', { name: 'Exportar CSV' }).click()])
const csv = readFileSync(await download.path(), 'utf8')
if (!csv.includes('Incidência;') || !csv.includes('planta;linha;estado') || !csv.includes('Dados simulados;sim')) {
  throw new Error('CSV sem o conteúdo esperado')
}
passo(`relatório: CSV exportado (${download.suggestedFilename()}, ${csv.split('\r\n').length} linhas)`)
await g.getByRole('button', { name: 'Imprimir / PDF' }).waitFor()
await g.emulateMedia({ media: 'print' })
if (await g.getByRole('navigation', { name: 'Navegação principal' }).isVisible()) throw new Error('menu aparece na impressão')
await g.emulateMedia({ media: 'screen' })
passo('relatório: impressão sem menu nem botões (PDF pelo navegador)')
await g.screenshot({ path: `${SHOTS}/83-relatorio.png`, fullPage: true })

await g.getByRole('link', { name: 'Comparar' }).click()
await g.locator('[data-comparacao]').getByText('Incidência antes').waitFor()
await g.getByText('Planta a planta').waitFor()
await g.getByText(/L1-P006/).first().waitFor()
passo('comparação entre missões: incidência antes/depois e planta a planta, com os dois mapas')
await g.screenshot({ path: `${SHOTS}/84-comparacao.png`, fullPage: true })

await g.goto(`${BASE}/talhoes/${dados.field_id}`)
await g.getByRole('link', { name: 'Linha do tempo' }).click()
const linha = g.locator('[data-linha-do-tempo]')
for (const etapa of ['Missão', 'Ocorrências', 'Prescrição', 'Aprovação', 'Aplicação', 'Verificação']) {
  await linha.getByText(etapa, { exact: true }).first().waitFor()
}
await linha.getByText(/a partir da varredura/).first().waitFor()
passo('linha do tempo do talhão: missão → ocorrências → prescrição → aprovação → aplicação → verificação')
await g.screenshot({ path: `${SHOTS}/85-linha-do-tempo.png`, fullPage: true })

await g.goto(`${BASE}/mapa?modo=missao&missao=${dados.missao2}`)
const camadas = g.locator('[data-camadas]')
await camadas.getByText('Umidade do solo').waitFor()
await camadas.getByText(/sem dado: Sem sensor de umidade/).waitFor()
if (await camadas.getByRole('checkbox').nth(7).isEnabled()) throw new Error('umidade habilitada sem dado')
await g.locator(`[data-mapa-missao="${dados.missao2}"] path.leaflet-interactive`).first().waitFor()
const pontos = await g.locator(`[data-mapa-missao="${dados.missao2}"] path.leaflet-interactive`).count()
await g.getByText(/54 planta\(s\)/).waitFor()
passo(`mapa por missão: plantas, eventos e rota desenhados (${pontos} elementos); umidade/falhas/produtividade sem dado inventado`)
await camadas.getByText('Mapa de calor (incidência)').click()
await g.getByLabel('Comparar com').selectOption(dados.missao1)
await camadas.getByText('Comparação entre passadas').click()
await g.getByText(/Recuperada · \d+/).waitFor()
passo('mapa: calor e comparação entre passadas (recuperada, persistente, nova)')
await g.screenshot({ path: `${SHOTS}/86-mapa-camadas.png`, fullPage: true })

// --- Operações: publicar e destinar pacote OTA pela tela ---------------------------------
const o = await entrar('ops.e2e@equipe.valtexa.dev')
await o.waitForURL('**/plataforma/**')
await o.getByRole('link', { name: 'Atualizações (OTA)' }).first().click()
await o.getByRole('button', { name: 'Publicar pacote' }).click()
const dlg = o.getByRole('dialog')
await dlg.getByLabel('Tipo do pacote').selectOption('model')
await dlg.getByText(/Nenhuma versão em PRODUÇÃO|versão\(ões\) em PRODUÇÃO com artefato/).first().waitFor()
await dlg.getByLabel('Tipo do pacote').selectOption('config')
await dlg.getByLabel('Versão do pacote').fill('cfg-e2e8')
await dlg.getByLabel('Arquivo do pacote').setInputFiles(dados.tar)
await dlg.getByRole('button', { name: 'Publicar' }).click()
await o.getByRole('dialog').getByText(/Destinar Configuração cfg-e2e8/).waitFor()
passo('OTA: pacote publicado pela tela (antes só pela API)')
await o.getByRole('dialog').getByRole('checkbox', { name: /Robô PAP-R-/ }).check()
await o.getByRole('dialog').getByRole('button', { name: 'Destinar' }).click()
await o.getByRole('row', { name: /cfg-e2e8.*PAP-R-/ }).getByText('Pendente').waitFor()
passo('OTA: destinado ao Rover e acompanhado (Pendente)')
await o.screenshot({ path: `${SHOTS}/87-ota-publicar.png`, fullPage: true })

// --- IA & Dados: registrar rodada dNATY pela tela ----------------------------------------
const i = await entrar('ia1.e2e@equipe.valtexa.dev')
await i.waitForURL('**/plataforma/**')
await i.goto(`${BASE}/plataforma/ia`)
await i.getByRole('row', { name: /9.9.8-e2e/ }).getByRole('button', { name: 'Abrir' }).click()
await i.getByRole('button', { name: 'Registrar rodada' }).click()
const rodada = i.locator('[data-registrar-rodada]')
await rodada.getByLabel('Relatório da otimização').setInputFiles(dados.relatorio_dnaty)
await rodada.getByText(/o relatório dizia aceito/).waitFor()
if (await rodada.getByRole('button', { name: 'Registrar' }).isEnabled()) throw new Error('registrar sem URI do otimizado')
await rodada.getByLabel('URI do otimizado').fill('s3://modelos/coffee/9.9.8-e2e/dnaty.onnx')
await rodada.getByRole('button', { name: 'Registrar' }).click()
await rodada.getByText(/Aceita: o otimizado passa a ser o da versão/).waitFor()
await i.getByText('É o otimizado atual').first().waitFor()
passo('dNATY: rodada registrada pela tela, aceita pelo critério do registry')
await i.screenshot({ path: `${SHOTS}/88-dnaty-registrar.png`, fullPage: true })

await b.close()
if (erros) {
  console.log(`${erros} erro(s) de JavaScript`)
  process.exit(1)
}
console.log(`${passos} de ${passos} passos ok, sem erro de JavaScript`)
