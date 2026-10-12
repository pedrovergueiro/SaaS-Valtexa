import { FormField } from '@/components/ui'
import { carProblem, documentProblem, type RegistryKey, type RegistryValues } from '@/lib/farmRegistry'

/**
 * Identificação da fazenda (produtor, documento, município, CAR, responsável
 * técnico). O mesmo bloco serve para criar e para completar o cadastro.
 */
export function FarmRegistryInputs({
  values,
  onChange,
}: {
  values: RegistryValues
  onChange: (key: RegistryKey, value: string) => void
}) {
  const docErro = documentProblem(values.owner_document)
  const carErro = carProblem(values.car_code)
  const campo = (key: RegistryKey) => ({
    value: values[key],
    onChange: (event: { target: { value: string } }) => onChange(key, event.target.value),
  })
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <FormField label="Proprietário ou produtor">
        <input className="input" {...campo('owner_name')} maxLength={160} placeholder="Maria Souza" />
      </FormField>
      <FormField label="CPF ou CNPJ" hint={docErro ?? 'Do proprietário. Pode digitar com pontos.'}>
        <input className="input num" {...campo('owner_document')} aria-invalid={Boolean(docErro)} maxLength={32} />
      </FormField>
      <FormField label="Município">
        <input className="input" {...campo('city')} maxLength={120} placeholder="Sorriso" />
      </FormField>
      <FormField label="UF">
        <input className="input w-20 uppercase" {...campo('state')} maxLength={2} placeholder="MT" />
      </FormField>
      <FormField label="Cultura principal">
        <input className="input" {...campo('main_crop')} maxLength={64} placeholder="Café" />
      </FormField>
      <FormField label="Responsável técnico" hint="Agrônomo responsável, com o registro no conselho.">
        <input className="input" {...campo('technical_lead')} maxLength={160} placeholder="Eng. Agr. Ana Lima — CREA-MT 12345" />
      </FormField>
      <div className="sm:col-span-2">
        <FormField label="Recibo do CAR" hint={carErro ?? 'Cadastro Ambiental Rural, como aparece no recibo.'}>
          <input className="input font-mono" {...campo('car_code')} aria-invalid={Boolean(carErro)} maxLength={64} />
        </FormField>
      </div>
      <div className="sm:col-span-2">
        <FormField label="Observações">
          <textarea className="input min-h-16" {...campo('notes')} maxLength={4000} />
        </FormField>
      </div>
    </div>
  )
}

export function registryHasErrors(values: RegistryValues): boolean {
  return Boolean(documentProblem(values.owner_document) || carProblem(values.car_code))
}
