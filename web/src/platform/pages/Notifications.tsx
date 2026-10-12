import { NotificationCenter } from '@/components/NotificationCenter'
import { PageHeader } from '@/components/ui'
import { usePlatformMe } from '@/platform/api'
import { PLATFORM_ROLES, platformRoleLabel } from '@/platform/labels'

/** Central de notificações da equipe (seção 48). O superadmin define o padrão por papel. */
export default function PlatformNotifications() {
  const me = usePlatformMe()
  const papeis = me.data?.capabilities.includes('platform:role:manage')
    ? PLATFORM_ROLES.map((value) => ({ value, label: platformRoleLabel(value) }))
    : undefined
  return (
    <>
      <PageHeader
        title="Notificações"
        subtitle="Chamados novos e respostas de clientes, atualizações que falharam nos robôs — e por onde você quer receber."
      />
      <NotificationCenter audience="plataforma" roles={papeis} />
    </>
  )
}
