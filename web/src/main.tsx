import 'leaflet/dist/leaflet.css'
import './app.css'

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { RouterProvider } from 'react-router-dom'

import { ApiError } from '@/api/client'
import { AuthProvider } from '@/auth/AuthProvider'
import { ToastProvider } from '@/components/ui'
import { ThemeProvider } from '@/lib/theme'
import { router } from '@/router'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 15_000,
      retry: (failures, error) => {
        // Erro do cliente (403, 404, 422) não melhora repetindo.
        if (error instanceof ApiError && error.status < 500) return false
        return failures < 2
      },
    },
  },
})

const root = document.getElementById('root')
if (!root) throw new Error('Elemento #root ausente no index.html')

createRoot(root).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <ToastProvider>
          <AuthProvider>
            <RouterProvider router={router} />
          </AuthProvider>
        </ToastProvider>
      </ThemeProvider>
    </QueryClientProvider>
  </StrictMode>,
)
