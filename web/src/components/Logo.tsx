import { cn } from '@/lib/cn'

/** Símbolo da ValTexa: o enquadramento da visão computacional e duas folhas. */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 64 64" className={cn('size-8', className)} role="img" aria-label="ValTexa">
      <g fill="none" stroke="var(--accent)" strokeWidth="3.4" strokeLinecap="round" opacity="0.9">
        <path d="M13 17v-3h9M51 17v-3h-9M13 47v3h9M51 47v3h-9" />
      </g>
      <path d="M32 47c0-11.5 5.6-19.6 14.4-22.6C45.3 37 40.2 44.2 32 47z" fill="var(--accent)" />
      <path d="M32 47c0-8.4-3.8-14.2-10.5-16.7C22.2 39.3 25.7 44.9 32 47z" fill="#0e6b4c" />
      <circle cx="32" cy="30" r="3.1" fill="var(--ink)" />
    </svg>
  )
}

export function Logo({ className }: { className?: string }) {
  return (
    <span className={cn('inline-flex items-center gap-2.5', className)}>
      <LogoMark />
      <span className="leading-none">
        <span className="font-display block text-[17px] font-semibold tracking-tight">ValTexa</span>
        <span className="block text-[11px] tracking-wide text-muted">Console</span>
      </span>
    </span>
  )
}
