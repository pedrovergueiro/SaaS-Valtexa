// Roteiro de navegador: Configurações do cliente (Meu plano, Dados no treino, Acessos
// da ValTexa), cadastro da fazenda e a "Saúde do sistema" no console da plataforma.
//
// Mesmos pré-requisitos de console-plataforma.mjs, mais a conta `dono@valtexa.dev`
// (papel proprietário no cliente de demonstração).
//
//   npm i --no-save playwright && node e2e/conta-e-fazenda.mjs /tmp
import { chromium } from 'playwright'
const BASE = 'http://localhost:8765'
const SHOTS = process.argv[2]
// Com o Chromium pré-instalado num caminho fixo: CHROMIUM_PATH=/opt/pw-browsers/chromium/...
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

// --- dono: Configurações ------------------------------------------------------
const p = await entrar('dono@valtexa.dev')
await p.getByRole('navigation', { name: 'Navegação principal' }).first().waitFor()
await p.goto(`${BASE}/configuracoes`)
await p.getByRole('tab', { name: 'Meu plano' }).waitFor()
const abas = await p.getByRole('tab').allInnerTexts()
if (abas.some((t) => /Plataforma/.test(t))) throw new Error('aba de plataforma no cliente: ' + abas)
passo('Configurações sem a aba "Plataforma": ' + abas.join(', '))

await p.getByRole('tab', { name: 'Meu plano' }).click()
await p.getByText('Sem plano contratado').first().waitFor()
passo('Meu plano: estado vazio com a próxima ação')

await p.getByRole('tab', { name: 'Dados no treino' }).click()
await p.getByText('vale NÃO').waitFor()
await p.getByLabel(/SIM — permitir/).check()
await p.getByRole('button', { name: 'Registrar decisão' }).click()
await p.getByText(/^SIM: as imagens desta conta/).waitFor()
await p.getByRole('cell', { name: 'dono@valtexa.dev' }).first().waitFor()
passo('dono registrou SIM; aparece no histórico com quem decidiu')
await p.screenshot({ path: `${SHOTS}/8-consentimento.png` })

await p.getByRole('tab', { name: 'Acessos da ValTexa' }).click()
await p.getByText('nunca entrou nesta conta').waitFor()
passo('Acessos da ValTexa: nenhuma entrada ainda')

// --- dono: cadastro da fazenda --------------------------------------------------
await p.goto(`${BASE}/talhoes`)
await p.getByText(/cadastro incompleto/).first().waitFor()
await p.getByRole('button', { name: 'Completar cadastro' }).first().click()
await p.getByLabel('Proprietário ou produtor').fill('Maria Souza')
await p.getByLabel('CPF ou CNPJ').fill('529.982.247-26')
await p.getByText('CPF inválido').waitFor()
if (!(await p.getByRole('button', { name: 'Salvar cadastro' }).isDisabled())) throw new Error('salvou CPF errado')
passo('CPF com dígito errado é recusado na tela')
await p.getByLabel('CPF ou CNPJ').fill('529.982.247-25')
await p.getByLabel('Município').fill('Sorriso')
await p.getByLabel('UF').fill('MT')
await p.getByLabel('Responsável técnico').fill('Eng. Agr. Ana Lima — CREA-MT 12345')
await p.getByLabel('Recibo do CAR').fill('MT-5107925-0123456789ABCDEF0123456789ABCDEF')
await p.getByRole('button', { name: 'Salvar cadastro' }).click()
await p.getByText('529.982.247-25').waitFor()
passo('cadastro salvo; a fazenda mostra produtor, CPF e município')
await p.screenshot({ path: `${SHOTS}/9-fazenda.png` })

// --- suporte: Saúde do sistema e entrada que o cliente vê ---------------------------
const s = await entrar('suporte@valtexa.dev')
await s.waitForURL('**/plataforma/clientes')
await s.goto(`${BASE}/plataforma/saude`)
await s.getByText('Pendências para produção').waitFor()
await s.getByText('SESSION_SECRET').first().waitFor()
passo('Saúde do sistema no console da plataforma, com o detalhe')
await s.screenshot({ path: `${SHOTS}/10-saude.png` })
await s.goto(`${BASE}/plataforma/clientes`)
await s.getByRole('button', { name: 'Entrar como cliente' }).first().click()
await s.fill('textarea', 'Chamado 77: conferir cadastro da fazenda')
await s.getByRole('button', { name: 'Entrar em modo leitura' }).click()
await s.waitForURL(`${BASE}/`)
await s.getByRole('button', { name: 'Sair do cliente' }).click()
await s.waitForURL('**/plataforma/clientes**')

await p.goto(`${BASE}/configuracoes`)
await p.getByRole('tab', { name: 'Acessos da ValTexa' }).click()
await p.getByText('Chamado 77').waitFor()
await p.getByText('Encerrada pela equipe').waitFor()
passo('o cliente vê a entrada do suporte, com motivo e situação')
await p.screenshot({ path: `${SHOTS}/11-acessos.png` })
await b.close()
