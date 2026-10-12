/** Rótulos do console interno, em português. */

const PAPEIS: Record<string, string> = {
  superadmin: 'Superadmin',
  suporte: 'Suporte',
  ia_dados: 'IA & Dados',
  operacoes: 'Operações',
  comercial: 'Comercial',
}

export const PLATFORM_ROLES = ['superadmin', 'suporte', 'ia_dados', 'operacoes', 'comercial'] as const

export function platformRoleLabel(role: string | null | undefined): string {
  if (!role) return 'Sem papel de plataforma'
  return PAPEIS[role] ?? role
}

const ASSINATURA: Record<string, string> = {
  teste: 'Em teste',
  ativa: 'Ativa',
  suspensa: 'Suspensa',
  cancelada: 'Cancelada',
}

export function subscriptionLabel(status: string | null | undefined): string {
  if (!status) return 'Sem plano'
  return ASSINATURA[status] ?? status
}
