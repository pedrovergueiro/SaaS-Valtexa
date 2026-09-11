import { ArrowRight, ShieldCheck } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Navigate, useNavigate, useSearchParams } from 'react-router-dom'

import { useAuth } from '@/auth/AuthProvider'
import { Logo } from '@/components/Logo'
import { Button, ErrorBox, FormField } from '@/components/ui'

const DEMO = [
  { email: 'agronomo@valtexa.dev', role: 'Agrônomo' },
  { email: 'operador@valtexa.dev', role: 'Operador' },
  { email: 'admin@valtexa.dev', role: 'Administrador' },
]

export default function Login() {
  const { session, login } = useAuth()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<unknown>(null)
  const [busy, setBusy] = useState(false)

  const next = params.get('next') || '/'
  if (session) return <Navigate to={next} replace />

  async function submit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await login(email.trim(), password)
      navigate(next, { replace: true })
    } catch (caught) {
      setError(caught)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="grid min-h-full lg:grid-cols-[1.1fr_1fr]">
      <section className="relative hidden overflow-hidden bg-[#07110e] p-12 text-[#e9f2ed] lg:flex lg:flex-col">
        <div
          className="absolute inset-0 opacity-60"
          style={{
            backgroundImage:
              'repeating-linear-gradient(115deg, rgb(47 224 139 / 0.07) 0 2px, transparent 2px 38px), radial-gradient(circle at 20% 80%, rgb(47 224 139 / 0.18), transparent 55%)',
          }}
          aria-hidden
        />
        <div className="relative">
          <span className="[--accent:#2fe08b] [--ink:#e9f2ed] [--muted:#9bb5aa]">
            <Logo />
          </span>
        </div>
        <div className="relative mt-auto max-w-lg">
          <h1 className="text-[40px] leading-[1.05] font-semibold">
            Da imagem à decisão.
            <br />
            <span className="text-[#2fe08b]">Com um agrônomo no meio.</span>
          </h1>
          <p className="mt-5 text-[15px] leading-relaxed text-[#a9c1b6]">
            O rover observa, a IA sugere, o agrônomo decide e a camada de segurança confere cada litro antes do
            drone decolar. Nenhum resultado de IA comanda uma aplicação.
          </p>
          <div className="mt-8 flex items-center gap-2 text-[13px] text-[#a9c1b6]">
            <ShieldCheck className="size-4 text-[#2fe08b]" aria-hidden />
            Comandos assinados com Ed25519 · auditoria completa · falha fechada
          </div>
        </div>
      </section>

      <section className="flex items-center justify-center p-6 sm:p-10">
        <form onSubmit={submit} className="w-full max-w-sm">
          <div className="mb-10 lg:hidden">
            <Logo />
          </div>
          <h2 className="text-[24px] font-semibold">Entrar no console</h2>
          <p className="mt-1 text-[14px] text-ink-2">Use a conta que a ValTexa criou para você.</p>

          <div className="mt-8 flex flex-col gap-4">
            <FormField label="E-mail">
              <input
                className="input"
                type="email"
                autoComplete="username"
                required
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="voce@fazenda.com.br"
              />
            </FormField>
            <FormField label="Senha">
              <input
                className="input"
                type="password"
                autoComplete="current-password"
                required
                minLength={8}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
            </FormField>
            <ErrorBox error={error} />
            <Button type="submit" variant="primary" loading={busy} className="mt-1 h-11">
              Entrar <ArrowRight className="size-4" aria-hidden />
            </Button>
          </div>

          {import.meta.env.DEV && (
            <div className="mt-10 rounded-[12px] border border-dashed border-line p-4">
              <div className="text-[12px] font-medium text-muted">Contas de demonstração (só em desenvolvimento)</div>
              <div className="mt-2 flex flex-wrap gap-2">
                {DEMO.map((account) => (
                  <button
                    key={account.email}
                    type="button"
                    onClick={() => {
                      setEmail(account.email)
                      setPassword('valtexa-demo-2026')
                    }}
                    className="rounded-full border border-line px-3 py-1 text-[12px] hover:bg-raised"
                  >
                    {account.role}
                  </button>
                ))}
              </div>
            </div>
          )}
        </form>
      </section>
    </div>
  )
}
