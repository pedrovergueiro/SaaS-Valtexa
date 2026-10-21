import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'

import { api } from '@/api/client'
import { useApiMutation } from '@/api/queries'
import { Badge, Button, Card, CardHeader, Empty, ErrorBox, FormField, Meter } from '@/components/ui'
import { avisoText, bytesText, classesOrdenadas, fracaoTone, prioridadeText, type RelatorioDados } from '@/lib/dados'
import { fmt } from '@/lib/format'

const GB = 1_000_000_000

/**
 * Consumo de dados pela Starlink do robô (rodada 4): o que o Rover contou hoje, o que a
 * plataforma recebeu, o teto e os avisos (tempestade de eventos, teto cruzado). Quem pode
 * gerenciar o robô muda o teto, que desce assinado na próxima missão.
 */
export function DadosStarlink({ deviceId, podeMudar }: { deviceId: string; podeMudar: boolean }) {
  const chave = ['devices', deviceId, 'dados']
  const rel = useQuery({
    queryKey: chave,
    queryFn: () => api<RelatorioDados>(`/v1/devices/${deviceId}/dados`, { query: { dias: 7 } }),
    refetchInterval: 60_000,
  })
  const [teto, setTeto] = useState('')
  const salvar = useApiMutation(
    (bytes_dia: number | null) =>
      api(`/v1/devices/${deviceId}/orcamento-dados`, { method: 'PUT', body: bytes_dia == null ? {} : { bytes_dia } }),
    [chave],
  )

  if (rel.error) return <ErrorBox error={rel.error} />
  const r = rel.data
  const contado = r?.contado_no_rover
  const classes = classesOrdenadas(contado?.por_classe)
  return (
    <Card>
      <CardHeader
        title="Dados pela Starlink"
        subtitle={r ? `Teto ${bytesText(r.teto.efetivo_dia_bytes)}/dia (${r.teto.origem === 'plataforma' ? 'da plataforma' : 'do rover.json'})` : 'Carregando'}
      />
      <div className="flex flex-col gap-3 px-5 pb-5 text-[13px]">
        {!contado && <Empty title="O robô ainda não contou o consumo" />}
        {contado && (
          <>
            <div className="flex items-center gap-2">
              <Meter value={r?.fracao_hoje ?? 0} tone={fracaoTone(r?.fracao_hoje, contado.tempestade)} label="Uso do teto do dia" />
              <span className="num w-40 text-right text-[12px]">
                {bytesText(contado.usado_bytes)} ({fmt.percent(r?.fracao_hoje)})
              </span>
            </div>
            {contado.tempestade && <Badge tone="serious">Tempestade de eventos: originais retidos no disco</Badge>}
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5">
              <dt className="text-muted">Subiu / desceu</dt>
              <dd className="num">{bytesText(contado.enviados_bytes)} / {bytesText(contado.recebidos_bytes)}</dd>
              <dt className="text-muted">Ainda sobe</dt>
              <dd>{prioridadeText(contado.prioridade_maxima_liberada)}</dd>
              <dt className="text-muted">Esperando o teto</dt>
              <dd className="num">{fmt.number(contado.adiados)} itens</dd>
              <dt className="text-muted">Retidos no disco</dt>
              <dd className="num">{fmt.number(contado.retidos)} itens</dd>
              {classes.map((c) => (
                <div key={c.classe} className="contents">
                  <dt className="text-muted">{c.rotulo}</dt>
                  <dd className="num">{bytesText(c.bytes)}</dd>
                </div>
              ))}
            </dl>
          </>
        )}
        {r && r.medido_na_plataforma.length > 0 && (
          <div>
            <p className="mb-1 text-[12px] text-muted">Recebido inteiro pela plataforma (sem cabeçalho nem descida)</p>
            <ul className="num text-[12px]">
              {r.medido_na_plataforma.map((d) => (
                <li key={d.dia} className="flex justify-between border-t border-line-soft py-1">
                  <span>{d.dia}</span>
                  <span>
                    {bytesText(d.total_bytes)} · {fmt.number(d.arquivos)} imagens · {fmt.number(d.registros)} registros
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}
        {r && r.avisos.length > 0 && (
          <ul className="text-[12px]">
            {r.avisos.slice(0, 5).map((a) => (
              <li key={`${a.tipo}-${a.em}`} className="flex justify-between border-t border-line-soft py-1">
                <span>{avisoText(a)}</span>
                <span className="text-muted">{fmt.ago(a.em)}</span>
              </li>
            ))}
          </ul>
        )}
        {podeMudar && (
          <form
            className="flex items-end gap-2"
            onSubmit={(e) => {
              e.preventDefault()
              const gb = Number(teto.replace(',', '.'))
              salvar.mutate(teto.trim() === '' ? null : Math.round(gb * GB))
            }}
          >
            <FormField label="Teto do dia (GB; vazio = o do robô)">
              <input className="input num w-28" inputMode="decimal" value={teto} onChange={(e) => setTeto(e.target.value)} />
            </FormField>
            <Button type="submit" disabled={salvar.isPending || (teto.trim() !== '' && !(Number(teto.replace(',', '.')) >= 0))}>
              Salvar
            </Button>
          </form>
        )}
        {salvar.error && <ErrorBox error={salvar.error} />}
      </div>
    </Card>
  )
}
