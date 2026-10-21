import { lazy, Suspense, type ComponentType } from 'react'
import { createBrowserRouter, Navigate, Outlet, useLocation } from 'react-router-dom'

import { useAuth } from '@/auth/AuthProvider'
import { Spinner } from '@/components/ui'
import { AppShell } from '@/layout/AppShell'
import { PlatformShell } from '@/platform/PlatformShell'
import Login from '@/pages/Login'
import NotFound from '@/pages/NotFound'
import TenantChooser from '@/pages/TenantChooser'

const RECARREGOU = 'valtexa:chunk-recarregado'

/**
 * `lazy` que sobrevive a um deploy com a aba aberta.
 *
 * O console é dividido em pedaços com o hash do conteúdo no nome. Depois de um
 * deploy, `Dashboard-j_LcjWdF.js` deixa de existir e a aba que já estava aberta
 * quebra com "Failed to fetch dynamically imported module" na primeira navegação
 * — não é erro de código, é a página antiga pedindo um arquivo que saiu do ar.
 *
 * A saída é recarregar uma vez: o `index.html` novo traz os nomes novos. A trava
 * em `sessionStorage` existe para que uma falha de rede de verdade não vire laço
 * de recarga — na segunda vez o erro sobe e aparece.
 */
function lazyPage(carregar: () => Promise<{ default: ComponentType }>) {
  return lazy(async () => {
    try {
      const modulo = await carregar()
      sessionStorage.removeItem(RECARREGOU)
      return modulo
    } catch (erro) {
      if (!sessionStorage.getItem(RECARREGOU)) {
        sessionStorage.setItem(RECARREGOU, '1')
        window.location.reload()
        // A recarga é assíncrona; esta promessa nunca precisa resolver.
        return await new Promise<never>(() => {})
      }
      throw erro
    }
  })
}

// Páginas com mapa e gráfico carregam sob demanda: Leaflet e Recharts pesam, e
// quem abre a fila do agrônomo no celular não precisa baixar os dois.
const Dashboard = lazyPage(() => import('@/pages/Dashboard'))
const MapPage = lazyPage(() => import('@/pages/MapPage'))
const Fleet = lazyPage(() => import('@/pages/Fleet'))
const DeviceDetail = lazyPage(() => import('@/pages/DeviceDetail'))
const Missions = lazyPage(() => import('@/pages/Missions'))
const MissionDetail = lazyPage(() => import('@/pages/MissionDetail'))
const MissionReportPage = lazyPage(() => import('@/pages/MissionReportPage'))
const MissionCompare = lazyPage(() => import('@/pages/MissionCompare'))
const FieldHistory = lazyPage(() => import('@/pages/FieldHistory'))
const Pareceres = lazyPage(() => import('@/pages/Pareceres'))
const ParecerDetail = lazyPage(() => import('@/pages/ParecerDetail'))
const Planejamento = lazyPage(() => import('@/pages/Planejamento'))
const PlanejamentoInsumos = lazyPage(() => import('@/pages/PlanejamentoInsumos'))
const PlanoDetail = lazyPage(() => import('@/pages/PlanoDetail'))
const Review = lazyPage(() => import('@/pages/Review'))
const Fields = lazyPage(() => import('@/pages/Fields'))
const FieldDetail = lazyPage(() => import('@/pages/FieldDetail'))
// three.js é o maior pedaço do console; só baixa quem abre a cópia 3D.
const Field3D = lazyPage(() => import('@/pages/Field3D'))
const Applications = lazyPage(() => import('@/pages/Applications'))
const Collections = lazyPage(() => import('@/pages/Collections'))
// Painel da ValTexa: só a equipe chega aqui, e o servidor confere de novo
// em cada rota. O carregamento sob demanda mantém o console do cliente leve.
const AdminCollections = lazyPage(() => import('@/pages/admin/Collections'))
const ImportCollection = lazyPage(() => import('@/pages/admin/ImportCollection'))
const AdminCollectionDetail = lazyPage(() => import('@/pages/admin/CollectionDetail'))
const Datasets = lazyPage(() => import('@/pages/admin/Datasets'))
const BoundaryEditor = lazyPage(() => import('@/pages/admin/BoundaryEditor'))
const AdminTenants = lazyPage(() => import('@/pages/admin/Tenants'))
const MissionPlanner = lazyPage(() => import('@/pages/admin/MissionPlanner'))
// Console interno (equipe ValTexa): layout e cor próprios, rota própria.
const PlatformClients = lazyPage(() => import('@/platform/pages/Clients'))
const PlatformUsers = lazyPage(() => import('@/platform/pages/Users'))
const PlatformAudit = lazyPage(() => import('@/platform/pages/Audit'))
const PlatformHealth = lazyPage(() => import('@/platform/pages/Health'))
const PlatformFleet = lazyPage(() => import('@/platform/pages/Fleet'))
const PlatformAi = lazyPage(() => import('@/platform/pages/Ai'))
const PlatformOta = lazyPage(() => import('@/platform/pages/Ota'))
const PlatformCommandCenter = lazyPage(() => import('@/platform/pages/CommandCenter'))
const PlatformCommandList = lazyPage(() => import('@/platform/pages/CommandCenter').then((m) => ({ default: m.CommandCenterList })))
const PlatformValidation = lazyPage(() => import('@/platform/pages/Validation'))
const PlatformNotifications = lazyPage(() => import('@/platform/pages/Notifications'))
const PlatformSupport = lazyPage(() => import('@/platform/pages/Support'))
const PlatformSupportTicket = lazyPage(() => import('@/platform/pages/SupportTicket'))
const PlatformObservability = lazyPage(() => import('@/platform/pages/Observability'))
const Observability = lazyPage(() => import('@/pages/Observability'))
const Notifications = lazyPage(() => import('@/pages/Notifications'))
const Support = lazyPage(() => import('@/pages/Support'))
const SupportTicket = lazyPage(() => import('@/pages/SupportTicket'))
const Inputs = lazyPage(() => import('@/pages/Inputs'))
const Audit = lazyPage(() => import('@/pages/Audit'))
const Settings = lazyPage(() => import('@/pages/Settings'))

function RequireSession() {
  const { session, me, loading, support } = useAuth()
  const location = useLocation()

  if (!session) {
    const next = location.pathname === '/' ? '' : `?next=${encodeURIComponent(location.pathname)}`
    return <Navigate to={`/entrar${next}`} replace />
  }
  // A equipe ValTexa não navega o console do cliente sem sessão de suporte: a
  // porta dela é o console da plataforma (brief, seção 29).
  if (session.platform && !support && (!session.tenantId || me?.access === 'plataforma')) {
    return <Navigate to="/plataforma" replace />
  }
  if (!session.tenantId) return <TenantChooser />
  if (loading && !me) {
    return (
      <div className="grid h-full place-items-center">
        <Spinner label="Abrindo o console" />
      </div>
    )
  }
  return (
    <AppShell>
      <Suspense fallback={<Spinner />}>
        <Outlet />
      </Suspense>
    </AppShell>
  )
}

function RequirePlatform() {
  const { session, support } = useAuth()
  const location = useLocation()
  if (!session) {
    return <Navigate to={`/entrar?next=${encodeURIComponent(location.pathname)}`} replace />
  }
  // Dentro de um cliente, o console da plataforma fica fechado até sair dele:
  // o token ativo é o do suporte, que não vale nas rotas da plataforma.
  if (support) return <Navigate to="/" replace />
  if (!session.platform) return <Navigate to="/" replace />
  return (
    <PlatformShell>
      <Suspense fallback={<Spinner />}>
        <Outlet />
      </Suspense>
    </PlatformShell>
  )
}

/** Endereços antigos do painel administrativo, levados ao console da plataforma. */
function Redirect({ to }: { to: string }) {
  const { pathname } = useLocation()
  return <Navigate to={pathname.replace(/^\/admin\/[^/]+/, to)} replace />
}

export const router = createBrowserRouter([
  {
    path: '/plataforma',
    element: <RequirePlatform />,
    children: [
      { index: true, element: <Navigate to="/plataforma/clientes" replace /> },
      { path: 'clientes', element: <PlatformClients /> },
      { path: 'cadastro', element: <AdminTenants /> },
      { path: 'usuarios', element: <PlatformUsers /> },
      { path: 'auditoria', element: <PlatformAudit /> },
      { path: 'planejamento', element: <MissionPlanner /> },
      { path: 'coletas', element: <AdminCollections /> },
      { path: 'coletas/nova', element: <ImportCollection /> },
      { path: 'coletas/:id', element: <AdminCollectionDetail /> },
      { path: 'dataset', element: <Datasets /> },
      { path: 'saude', element: <PlatformHealth /> },
      { path: 'observabilidade', element: <PlatformObservability /> },
      { path: 'frota', element: <PlatformFleet /> },
      { path: 'comando', element: <PlatformCommandList /> },
      { path: 'comando/:id', element: <PlatformCommandCenter /> },
      { path: 'comando/:id/validacao', element: <PlatformValidation /> },
      { path: 'ia', element: <PlatformAi /> },
      { path: 'atualizacoes', element: <PlatformOta /> },
      { path: 'notificacoes', element: <PlatformNotifications /> },
      { path: 'suporte', element: <PlatformSupport /> },
      { path: 'suporte/:id', element: <PlatformSupportTicket /> },
      { path: '*', element: <NotFound /> },
    ],
  },
  { path: '/entrar', element: <Login /> },
  {
    element: <RequireSession />,
    children: [
      { index: true, element: <Dashboard /> },
      { path: 'mapa', element: <MapPage /> },
      { path: 'frota', element: <Fleet /> },
      { path: 'frota/:id', element: <DeviceDetail /> },
      { path: 'observabilidade', element: <Observability /> },
      { path: 'missoes', element: <Missions /> },
      { path: 'missoes/comparar', element: <MissionCompare /> },
      { path: 'missoes/:id', element: <MissionDetail /> },
      { path: 'missoes/:id/relatorio', element: <MissionReportPage /> },
      { path: 'revisao', element: <Review /> },
      { path: 'talhoes', element: <Fields /> },
      { path: 'talhoes/:id', element: <FieldDetail /> },
      { path: 'talhoes/:id/historico', element: <FieldHistory /> },
      { path: 'talhoes/:id/pareceres', element: <Pareceres /> },
      { path: 'pareceres/:id', element: <ParecerDetail /> },
      { path: 'talhoes/:id/planejamento', element: <Planejamento /> },
      { path: 'planejamento/insumos', element: <PlanejamentoInsumos /> },
      { path: 'planejamento/:id', element: <PlanoDetail /> },
      { path: 'lavoura-3d', element: <Field3D /> },
      { path: 'lavoura-3d/:id', element: <Field3D /> },
      { path: 'coletas', element: <Collections /> },
      { path: 'aplicacoes', element: <Applications /> },
      { path: 'insumos', element: <Inputs /> },
      { path: 'auditoria', element: <Audit /> },
      { path: 'configuracoes', element: <Settings /> },
      { path: 'notificacoes', element: <Notifications /> },
      { path: 'suporte', element: <Support /> },
      { path: 'suporte/:id', element: <SupportTicket /> },
      { path: 'admin/coletas/*', element: <Redirect to="/plataforma/coletas" /> },
      { path: 'admin/coletas', element: <Navigate to="/plataforma/coletas" replace /> },
      { path: 'admin/dataset', element: <Navigate to="/plataforma/dataset" replace /> },
      { path: 'admin/clientes', element: <Navigate to="/plataforma/cadastro" replace /> },
      { path: 'admin/planejamento', element: <Navigate to="/plataforma/planejamento" replace /> },
      { path: 'talhoes/:id/contorno', element: <BoundaryEditor /> },
      { path: '*', element: <NotFound /> },
    ],
  },
])
