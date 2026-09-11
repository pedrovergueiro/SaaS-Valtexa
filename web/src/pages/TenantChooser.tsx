import { Building2, ChevronRight } from 'lucide-react'

import { useAuth } from '@/auth/AuthProvider'
import { Logo } from '@/components/Logo'
import { Button, Empty, Spinner } from '@/components/ui'
import { role } from '@/lib/labels'

/** Para quem atende mais de um cliente: o agrônomo de cooperativa, a revenda. */
export default function TenantChooser() {
  const { memberships, selectTenant, logout, loading } = useAuth()

  return (
    <div className="grid min-h-full place-items-center p-6">
      <div className="w-full max-w-md">
        <Logo />
        <h1 className="mt-10 text-[22px] font-semibold">Qual cliente você quer abrir?</h1>
        <p className="mt-1 text-[14px] text-ink-2">Dá para trocar depois, pelo topo da tela.</p>

        <div className="card mt-6 overflow-hidden">
          {loading && <Spinner />}
          {!loading && memberships.length === 0 && (
            <Empty title="Nenhum cliente associado">Peça a um administrador para incluir você.</Empty>
          )}
          <ul>
            {memberships.map((item) => (
              <li key={item.tenant_id} className="border-b border-line-soft last:border-0">
                <button
                  type="button"
                  onClick={() => selectTenant(item.tenant_id)}
                  className="flex w-full items-center gap-3 px-4 py-3.5 text-left hover:bg-raised"
                >
                  <Building2 className="size-5 text-muted" aria-hidden />
                  <span className="flex-1">
                    <span className="block font-medium">{item.tenant_name}</span>
                    <span className="block text-[12px] text-muted">{role(item.role)}</span>
                  </span>
                  <ChevronRight className="size-4 text-muted" aria-hidden />
                </button>
              </li>
            ))}
          </ul>
        </div>
        <Button variant="ghost" className="mt-4" onClick={logout}>
          Sair
        </Button>
      </div>
    </div>
  )
}
