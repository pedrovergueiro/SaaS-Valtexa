import { Compass } from 'lucide-react'
import { Link } from 'react-router-dom'

import { Button, Empty } from '@/components/ui'

export default function NotFound() {
  return (
    <div className="card">
      <Empty
        title="Esta página não existe"
        icon={<Compass className="size-5" />}
        action={
          <Link to="/">
            <Button variant="primary">Voltar ao painel</Button>
          </Link>
        }
      >
        O endereço pode ter mudado, ou o item é de outro cliente.
      </Empty>
    </div>
  )
}
