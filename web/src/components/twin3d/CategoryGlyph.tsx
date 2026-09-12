import type { Category } from './FieldScene'

/** Cor de cada categoria — as mesmas que a cena usa, resolvidas pelo CSS. */
export const CATEGORY_COLOR: Record<Category, string> = {
  pest: 'var(--cat-pest)',
  disease: 'var(--series-2)',
  review: 'var(--series-1)',
  other: 'var(--series-other)',
  healthy: 'var(--series-3)',
}

/**
 * O símbolo da categoria, igual ao marcador da cena: forma e cor juntas.
 * Losango é praga, círculo é doença, triângulo espera o agrônomo, quadrado é
 * outro achado — a forma sozinha já distingue, para quem não separa as cores.
 */
export function CategoryGlyph({ category, size = 14 }: { category: Category; size?: number }) {
  const c = 50
  const r = 38
  let shape
  switch (category) {
    case 'pest':
      shape = <polygon points={`${c},${c - r} ${c + r},${c} ${c},${c + r} ${c - r},${c}`} />
      break
    case 'review':
      shape = <polygon points={`${c - r},${c - r * 0.75} ${c + r},${c - r * 0.75} ${c},${c + r}`} />
      break
    case 'other':
      shape = <rect x={c - r * 0.78} y={c - r * 0.78} width={r * 1.56} height={r * 1.56} />
      break
    default:
      shape = <circle cx={c} cy={c} r={r} />
  }
  return (
    <svg viewBox="0 0 100 100" width={size} height={size} aria-hidden className="shrink-0">
      <g
        fill={CATEGORY_COLOR[category]}
        stroke="var(--surface)"
        strokeWidth={11}
        strokeLinejoin="round"
        paintOrder="stroke"
      >
        {shape}
      </g>
    </svg>
  )
}
