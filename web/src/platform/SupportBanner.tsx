import { LogOut, PenLine, ShieldAlert, Eye } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { api } from '@/api/client'
import { useAuth } from '@/auth/AuthProvider'
import { Button, ErrorBox, FormField, Modal } from '@/components/ui'
import { minutesLeft } from '@/platform/support'

/**
 * A faixa de "entrar como cliente" (brief, seção 29: nunca acesso silencioso).
 *
 * Fica no topo de toda tela do console do cliente enquanto a sessão de suporte
 * durar, com cliente, modo, prazo e motivo — para quem está dentro não esquecer
 * onde está, e para quem olha a tela por cima do ombro saber o que está vendo.
 */
export function SupportBanner() {
  const { support, exitSupport, setSupportMode } = useAuth()
  const navigate = useNavigate()
  const [agora, setAgora] = useState(() => Date.now())
  const [pedindoAssistido, setPedindoAssistido] = useState(false)
  const [motivo, setMotivo] = useState('')
  const [erro, setErro] = useState<unknown>(null)
  const [ocupado, setOcupado] = useState(false)

  useEffect(() => {
    const timer = window.setInterval(() => setAgora(Date.now()), 30_000)
    return () => window.clearInterval(timer)
  }, [])

  if (!support) return null
  const assistido = support.mode === 'assistido'
  const tenantId = support.tenantId

  async function mudarModo(mode: 'leitura' | 'assistido', reason: string) {
    if (!support) return
    setOcupado(true)
    setErro(null)
    try {
      await api(`/v1/platform/support-sessions/${support.id}/mode`, {
        method: 'POST',
        body: { mode, reason },
      })
      setSupportMode(mode)
      setPedindoAssistido(false)
      setMotivo('')
    } catch (error) {
      setErro(error)
    } finally {
      setOcupado(false)
    }
  }

  async function sair() {
    setOcupado(true)
    await exitSupport()
    navigate(`/plataforma/clientes?aberto=${tenantId}`)
  }

  return (
    <div
      role="status"
      className={
        'flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-2 text-[13px] sm:px-6 lg:px-8 ' +
        (assistido ? 'bg-critical text-white' : 'bg-[#4338ca] text-white')
      }
    >
      <ShieldAlert className="size-4 shrink-0" aria-hidden />
      <span className="font-semibold">Suporte ValTexa em {support.tenantName}</span>
      <span className="rounded-full bg-white/20 px-2 py-0.5 text-[12px] font-medium">
        {assistido ? 'Modo assistido — alterações valem para o cliente' : 'Modo leitura'}
      </span>
      <span className="opacity-90">termina em {minutesLeft(support.expiresAt, agora)} min</span>
      <span className="hidden min-w-0 flex-1 truncate opacity-80 md:inline" title={support.reason}>
        Motivo: {support.reason}
      </span>
      <span className="ml-auto flex gap-2">
        {assistido ? (
          <Button
            size="sm"
            variant="ghost"
            className="text-white hover:bg-white/15 hover:text-white"
            icon={<Eye className="size-4" />}
            loading={ocupado}
            onClick={() => mudarModo('leitura', 'Voltou ao modo leitura.')}
          >
            Voltar a só ler
          </Button>
        ) : (
          <Button
            size="sm"
            variant="ghost"
            className="text-white hover:bg-white/15 hover:text-white"
            icon={<PenLine className="size-4" />}
            onClick={() => setPedindoAssistido(true)}
          >
            Modo assistido
          </Button>
        )}
        <Button
          size="sm"
          variant="secondary"
          icon={<LogOut className="size-4" />}
          loading={ocupado}
          onClick={sair}
        >
          Sair do cliente
        </Button>
      </span>

      <Modal
        open={pedindoAssistido}
        onClose={() => setPedindoAssistido(false)}
        title="Ligar o modo assistido"
        description="Com ele você altera dados em nome do cliente. Cada alteração fica na auditoria do cliente com o seu nome e este motivo."
        footer={
          <>
            <Button variant="ghost" onClick={() => setPedindoAssistido(false)}>
              Cancelar
            </Button>
            <Button
              variant="danger"
              loading={ocupado}
              disabled={motivo.trim().length < 10}
              onClick={() => mudarModo('assistido', motivo.trim())}
            >
              Ligar escrita
            </Button>
          </>
        }
      >
        <FormField label="Motivo" hint="Pelo menos 10 caracteres. O cliente vê este texto.">
          <textarea
            className="input min-h-24"
            value={motivo}
            onChange={(event) => setMotivo(event.target.value)}
            placeholder="Ex.: o cliente pediu para corrigir o espaçamento do talhão B (chamado 42)"
          />
        </FormField>
        <ErrorBox error={erro} className="mt-3" />
      </Modal>
    </div>
  )
}
