import { FormField } from '@/components/ui'

type SpacingValues = { spacing: string; plantSpacing: string; rowCount: string; validation: string; notes: string }
type SpacingSetters = {
  setSpacing: (value: string) => void
  setPlantSpacing: (value: string) => void
  setRowCount: (value: string) => void
  setValidation: (value: string) => void
  setNotes: (value: string) => void
}

/**
 * Os campos do talhão que a fusão por planta e a validação de campo usam. O
 * mesmo bloco serve para criar e para editar (`FieldDetail`).
 */
export function FieldSpacingInputs({
  values,
  setters,
  validationError,
}: {
  values: SpacingValues
  setters: SpacingSetters
  validationError: string | null
}) {
  return (
    <div className="grid gap-4 sm:grid-cols-3">
      <FormField label="Espaçamento entre linhas (m)" hint="Entre uma rua e outra.">
        <input className="input num" inputMode="decimal" value={values.spacing} onChange={(event) => setters.setSpacing(event.target.value)} placeholder="3,5" />
      </FormField>
      <FormField label="Espaçamento entre plantas (m)" hint="Na linha. A fusão separa as plantas por ele.">
        <input className="input num" inputMode="decimal" value={values.plantSpacing} onChange={(event) => setters.setPlantSpacing(event.target.value)} placeholder="2,5" />
      </FormField>
      <FormField label="Número de linhas">
        <input className="input num" inputMode="numeric" value={values.rowCount} onChange={(event) => setters.setRowCount(event.target.value)} placeholder="40" />
      </FormField>
      <div className="sm:col-span-3">
        <FormField
          label="Fileiras de validação"
          hint={validationError ?? 'Linhas em que o agrônomo rotula toda planta, para medir a IA. Ex.: 3, 10, 17 ou 3-5.'}
        >
          <input
            className="input font-mono"
            value={values.validation}
            onChange={(event) => setters.setValidation(event.target.value)}
            aria-invalid={Boolean(validationError)}
            placeholder="3, 10, 17"
          />
        </FormField>
      </div>
      <div className="sm:col-span-3">
        <FormField label="Observações">
          <textarea className="input min-h-16" value={values.notes} onChange={(event) => setters.setNotes(event.target.value)} maxLength={4000} />
        </FormField>
      </div>
    </div>
  )
}
