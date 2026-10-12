import { useAuth } from '@/auth/AuthProvider'
import { NotificationCenter } from '@/components/NotificationCenter'
import { PageHeader } from '@/components/ui'
import { role as roleLabel, ROLES } from '@/lib/labels'

/** Central de notificações do cliente (seção 48). O gestor define o padrão por papel. */
export default function Notifications() {
  const { can } = useAuth()
  const papeis = can('user:manage') ? ROLES.map((value) => ({ value, label: roleLabel(value) })) : undefined
  return (
    <>
      <PageHeader
        eyebrow="Governança"
        title="Notificações"
        subtitle="Avisos de infecção, incidência, missão bloqueada, robô offline, atualização que falhou e chamados — e por onde você quer recebê-los."
      />
      <NotificationCenter audience="cliente" roles={papeis} />
    </>
  )
}
