import { lazy, Suspense } from 'react'
import { createBrowserRouter, Navigate, Outlet, useLocation } from 'react-router-dom'

import { useAuth } from '@/auth/AuthProvider'
import { Spinner } from '@/components/ui'
import { AppShell } from '@/layout/AppShell'
import Login from '@/pages/Login'
import NotFound from '@/pages/NotFound'
import TenantChooser from '@/pages/TenantChooser'

// Páginas com mapa e gráfico carregam sob demanda: Leaflet e Recharts pesam, e
// quem abre a fila do agrônomo no celular não precisa baixar os dois.
const Dashboard = lazy(() => import('@/pages/Dashboard'))
const MapPage = lazy(() => import('@/pages/MapPage'))
const Fleet = lazy(() => import('@/pages/Fleet'))
const DeviceDetail = lazy(() => import('@/pages/DeviceDetail'))
const Missions = lazy(() => import('@/pages/Missions'))
const MissionDetail = lazy(() => import('@/pages/MissionDetail'))
const Review = lazy(() => import('@/pages/Review'))
const Fields = lazy(() => import('@/pages/Fields'))
const FieldDetail = lazy(() => import('@/pages/FieldDetail'))
const Applications = lazy(() => import('@/pages/Applications'))
const Inputs = lazy(() => import('@/pages/Inputs'))
const Audit = lazy(() => import('@/pages/Audit'))
const Settings = lazy(() => import('@/pages/Settings'))

function RequireSession() {
  const { session, me, loading } = useAuth()
  const location = useLocation()

  if (!session) {
    const next = location.pathname === '/' ? '' : `?next=${encodeURIComponent(location.pathname)}`
    return <Navigate to={`/entrar${next}`} replace />
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

export const router = createBrowserRouter([
  { path: '/entrar', element: <Login /> },
  {
    element: <RequireSession />,
    children: [
      { index: true, element: <Dashboard /> },
      { path: 'mapa', element: <MapPage /> },
      { path: 'frota', element: <Fleet /> },
      { path: 'frota/:id', element: <DeviceDetail /> },
      { path: 'missoes', element: <Missions /> },
      { path: 'missoes/:id', element: <MissionDetail /> },
      { path: 'revisao', element: <Review /> },
      { path: 'talhoes', element: <Fields /> },
      { path: 'talhoes/:id', element: <FieldDetail /> },
      { path: 'aplicacoes', element: <Applications /> },
      { path: 'insumos', element: <Inputs /> },
      { path: 'auditoria', element: <Audit /> },
      { path: 'configuracoes', element: <Settings /> },
      { path: '*', element: <NotFound /> },
    ],
  },
])
