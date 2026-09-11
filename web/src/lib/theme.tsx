import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'

/**
 * Tema: sistema, claro ou escuro.
 *
 * "Sistema" não carimba nada no <html> — quem decide é o `prefers-color-scheme`
 * no CSS. Claro e escuro carimbam `data-theme`, que vence nos dois sentidos.
 * No campo, sob sol, o claro é o legível; à noite na sede, o escuro.
 *
 * O carimbo é aplicado **antes** de o estado mudar: gráficos e mapa leem as
 * cores resolvidas do CSS durante a renderização, e um carimbo aplicado depois
 * (num efeito) os faria desenhar com as cores do tema anterior.
 */

export type ThemeChoice = 'system' | 'light' | 'dark'

const KEY = 'valtexa.theme'

type ThemeContextValue = {
  choice: ThemeChoice
  resolved: 'light' | 'dark'
  setChoice: (choice: ThemeChoice) => void
}

const ThemeContext = createContext<ThemeContextValue | null>(null)

function readChoice(): ThemeChoice {
  try {
    const stored = localStorage.getItem(KEY)
    if (stored === 'light' || stored === 'dark' || stored === 'system') return stored
  } catch {
    // modo privado ou armazenamento bloqueado: segue o sistema
  }
  return 'system'
}

function stamp(choice: ThemeChoice): void {
  const root = document.documentElement
  if (choice === 'system') root.removeAttribute('data-theme')
  else root.setAttribute('data-theme', choice)
}

function systemPrefersDark(): boolean {
  return window.matchMedia('(prefers-color-scheme: dark)').matches
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [choice, setChoiceState] = useState<ThemeChoice>(() => {
    const initial = readChoice()
    stamp(initial)
    return initial
  })
  const [systemDark, setSystemDark] = useState(systemPrefersDark)

  useEffect(() => {
    const media = window.matchMedia('(prefers-color-scheme: dark)')
    const listener = (event: MediaQueryListEvent) => setSystemDark(event.matches)
    media.addEventListener('change', listener)
    return () => media.removeEventListener('change', listener)
  }, [])

  const setChoice = useCallback((next: ThemeChoice) => {
    stamp(next)
    setChoiceState(next)
    try {
      localStorage.setItem(KEY, next)
    } catch {
      // sem armazenamento, o tema vale só para esta sessão
    }
  }, [])

  const resolved = choice === 'system' ? (systemDark ? 'dark' : 'light') : choice

  return <ThemeContext.Provider value={{ choice, resolved, setChoice }}>{children}</ThemeContext.Provider>
}

export function useTheme(): ThemeContextValue {
  const value = useContext(ThemeContext)
  if (!value) throw new Error('useTheme fora do ThemeProvider')
  return value
}
