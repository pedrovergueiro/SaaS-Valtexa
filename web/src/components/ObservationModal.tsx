import { Link } from 'react-router-dom'

import type { ObservationOut } from '@/api/types'
import { AuthImage } from '@/components/AuthImage'
import { Badge, Button, Modal } from '@/components/ui'
import { fmt } from '@/lib/format'
import { diagnosisStatus, diagnosisTone, disease } from '@/lib/labels'

export function ObservationModal({
  observation,
  onClose,
  showFieldLink = true,
}: {
  observation: ObservationOut | null
  onClose: () => void
  showFieldLink?: boolean
}) {
  return (
    <Modal
      open={Boolean(observation)}
      onClose={onClose}
      title={observation ? disease(observation.label) : ''}
      description={observation ? fmt.dateTime(observation.captured_at) : undefined}
      footer={
        <>
          <Button onClick={onClose}>Fechar</Button>
          {observation && showFieldLink && (
            <Link to={`/talhoes/${observation.field_id}`}>
              <Button variant="primary">Abrir talhão</Button>
            </Link>
          )}
        </>
      }
    >
      {observation && (
        <div className="flex flex-col gap-3">
          <AuthImage
            path={observation.image_asset_id ? `/v1/observations/${observation.id}/image` : null}
            alt="Folha observada"
            className="aspect-[4/3] w-full rounded-[10px]"
          />
          <div className="flex flex-wrap items-center gap-2 text-[13px]">
            <Badge tone={diagnosisTone(observation.diagnosis_status)}>{diagnosisStatus(observation.diagnosis_status)}</Badge>
            {observation.confidence != null && <span className="text-ink-2">confiança {fmt.percent(observation.confidence)}</span>}
            {observation.novelty_score != null && (
              <span className="text-ink-2">novidade {fmt.number(observation.novelty_score, 2)}</span>
            )}
            {observation.severity != null && (
              <span className="text-ink-2">área lesionada {fmt.percent(observation.severity)}</span>
            )}
          </div>
          <div className="num text-[12px] text-muted">
            {fmt.number(observation.lat, 6)}, {fmt.number(observation.lon, 6)}
          </div>
        </div>
      )}
    </Modal>
  )
}
