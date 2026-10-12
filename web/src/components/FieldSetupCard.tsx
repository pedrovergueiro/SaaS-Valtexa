import { ClipboardList, Pencil } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'

import { api } from '@/api/client'
import { keys, useApiMutation } from '@/api/queries'
import type { FieldOut } from '@/api/types'
import { FieldSpacingInputs } from '@/components/FieldSpacingInputs'
import { Button, Card, CardHeader, ErrorBox, FormField, Modal } from '@/components/ui'
import { fieldSetupGaps, formatValidationRows, optionalNumber, parseValidationRows } from '@/lib/fieldSetup'
import { fmt } from '@/lib/format'

/**
 * A configuração agronômica do talhão e o que falta nela, com a próxima ação
 * (brief, seção 5: espaçamento entre linhas e plantas, número de linhas,
 * fileiras de validação, observações).
 */
export function FieldSetupCard({ field, canManage }: { field: FieldOut; canManage: boolean }) {
  const [editando, setEditando] = useState(false)
  const faltas = fieldSetupGaps(field)
  const linhas: [string, string][] = [
    ['Entre linhas', field.row_spacing_m ? `${fmt.number(field.row_spacing_m, 2)} m` : '—'],
    ['Entre plantas', field.plant_spacing_m ? `${fmt.number(field.plant_spacing_m, 2)} m` : '—'],
    ['Direção das linhas', field.row_azimuth_deg != null ? `${fmt.number(field.row_azimuth_deg)}°` : '—'],
    ['Número de linhas', field.row_count ? fmt.number(field.row_count) : '—'],
    ['Fileiras de validação', field.validation_rows?.length ? formatValidationRows(field.validation_rows) : '—'],
  ]

  return (
    <Card className="mt-4">
      <CardHeader
        title="Cadastro do talhão"
        subtitle="O que a fusão por planta e a validação de campo usam."
        actions={
          canManage && (
            <Button size="sm" icon={<Pencil className="size-4" />} onClick={() => setEditando(true)}>
              Editar
            </Button>
          )
        }
      />
      <div className="grid gap-4 px-5 pb-5 lg:grid-cols-[1fr_1fr]">
        <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-[13px]">
          {linhas.map(([rotulo, valor]) => (
            <div key={rotulo} className="contents">
              <dt className="text-muted">{rotulo}</dt>
              <dd className="num font-medium">{valor}</dd>
            </div>
          ))}
          {field.notes && (
            <>
              <dt className="text-muted">Observações</dt>
              <dd className="whitespace-pre-line">{field.notes}</dd>
            </>
          )}
        </dl>
        {faltas.length === 0 ? (
          <div className="flex items-start gap-2 rounded-[10px] bg-accent-soft px-3 py-2.5 text-[13px]">
            <ClipboardList className="mt-0.5 size-4" aria-hidden />
            Cadastro completo para a fusão por planta e a validação de campo.
          </div>
        ) : (
          <ul className="flex flex-col gap-2" aria-label="O que falta no cadastro">
            {faltas.map((falta) => (
              <li key={falta.key} className="rounded-[10px] border border-warning/40 bg-warning/10 px-3 py-2.5 text-[13px]">
                <div>{falta.message}</div>
                {canManage &&
                  (falta.key === 'contorno' ? (
                    <Link to={`/talhoes/${field.id}/contorno`} className="mt-1 inline-block font-medium underline underline-offset-2">
                      {falta.action}
                    </Link>
                  ) : (
                    <button type="button" className="mt-1 font-medium underline underline-offset-2" onClick={() => setEditando(true)}>
                      {falta.action}
                    </button>
                  ))}
                {!canManage && <div className="mt-1 text-muted">Peça a quem administra a conta.</div>}
              </li>
            ))}
          </ul>
        )}
      </div>
      {editando && <FieldConfigModal field={field} onClose={() => setEditando(false)} />}
    </Card>
  )
}

function FieldConfigModal({ field, onClose }: { field: FieldOut; onClose: () => void }) {
  const texto = (valor: number | null | undefined) => (valor == null ? '' : String(valor).replace('.', ','))
  const [name, setName] = useState(field.name)
  const [variety, setVariety] = useState(field.variety ?? '')
  const [stage, setStage] = useState(field.crop_stage ?? '')
  const [azimuth, setAzimuth] = useState(texto(field.row_azimuth_deg))
  const [spacing, setSpacing] = useState(texto(field.row_spacing_m))
  const [plantSpacing, setPlantSpacing] = useState(texto(field.plant_spacing_m))
  const [rowCount, setRowCount] = useState(texto(field.row_count))
  const [validation, setValidation] = useState(formatValidationRows(field.validation_rows ?? []))
  const [notes, setNotes] = useState(field.notes ?? '')
  const fileiras = parseValidationRows(validation, optionalNumber(rowCount))

  const salvar = useApiMutation(
    () =>
      api<FieldOut>(`/v1/fields/${field.id}`, {
        method: 'PATCH',
        body: {
          name: name.trim(),
          variety: variety.trim() || null,
          crop_stage: stage.trim() || null,
          row_azimuth_deg: optionalNumber(azimuth),
          row_spacing_m: optionalNumber(spacing),
          plant_spacing_m: optionalNumber(plantSpacing),
          row_count: optionalNumber(rowCount),
          validation_rows: fileiras.rows,
          notes: notes.trim() || null,
        },
      }),
    [keys.field(field.id), keys.fields],
  )

  return (
    <Modal
      open
      onClose={onClose}
      wide
      title={`Configurar ${field.name}`}
      description="Cada alteração fica na auditoria do talhão, com o antes e o depois."
      footer={
        <>
          <Button onClick={onClose}>Cancelar</Button>
          <Button
            variant="primary"
            loading={salvar.isPending}
            disabled={!name.trim() || Boolean(fileiras.error)}
            onClick={() => salvar.mutate(undefined, { onSuccess: onClose })}
          >
            Salvar
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        <div className="grid gap-4 sm:grid-cols-4">
          <FormField label="Nome">
            <input className="input" value={name} onChange={(event) => setName(event.target.value)} />
          </FormField>
          <FormField label="Variedade">
            <input className="input" value={variety} onChange={(event) => setVariety(event.target.value)} />
          </FormField>
          <FormField label="Estágio">
            <input className="input" value={stage} onChange={(event) => setStage(event.target.value)} />
          </FormField>
          <FormField label="Direção das linhas (°)" hint="0 = N-S · 90 = L-O">
            <input className="input num" inputMode="decimal" value={azimuth} onChange={(event) => setAzimuth(event.target.value)} />
          </FormField>
        </div>
        <FieldSpacingInputs
          values={{ spacing, plantSpacing, rowCount, validation, notes }}
          setters={{ setSpacing, setPlantSpacing, setRowCount, setValidation, setNotes }}
          validationError={fileiras.error}
        />
        <ErrorBox error={salvar.error} />
      </div>
    </Modal>
  )
}
