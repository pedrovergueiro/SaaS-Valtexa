import { GraduationCap } from 'lucide-react'
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'

import { api } from '@/api/client'
import { useAuth } from '@/auth/AuthProvider'
import { Badge, Card, CardHeader, Empty, ErrorBox, Meter, PageHeader, Spinner, Stat, Table, Tabs, td, th } from '@/components/ui'
import { tendencia, type Painel } from '@/lib/ensino'
import { fmt } from '@/lib/format'
import { disease } from '@/lib/labels'
import { Regras, SegundaOpiniao } from '@/pages/EnsinoAbas'

type De = 'mim' | 'todos'
type Aba = 'painel' | 'opiniao' | 'regras'

/**
 * O que a IA aprendeu com o agrônomo: cada lição (o rótulo, o porquê, as lesões marcadas), onde
 * a IA mais erra com ele, o acerto dela mês a mês e as classes novas que ele está ensinando.
 */
export default function Ensino() {
  const { can } = useAuth()
  const [aba, setAba] = useState<Aba>('painel')
  const [de, setDe] = useState<De>('mim')
  const q = useQuery({ queryKey: ['ensino', 'painel', de], queryFn: () => api<Painel>('/v1/ensino/painel', { query: { de } }) })
  const d = q.data
  const t = d ? tendencia(d.acerto_da_ia_por_mes) : null
  return (
    <>
      <PageHeader
        eyebrow="Ensino"
        title="O que a IA aprendeu com você"
        subtitle="Cada diagnóstico na fila é uma lição. Com o porquê e a lesão marcada, ela vale muito mais: a IA aprende onde olhar, e os próximos pareceres citam o que você ensinou."
        actions={
          <>
            <Tabs<Aba>
              value={aba}
              onChange={setAba}
              items={[
                { value: 'painel', label: 'O que aprendeu' },
                { value: 'opiniao', label: 'Segunda opinião' },
                { value: 'regras', label: 'Regras' },
              ]}
            />
            {aba === 'painel' && (
              <Tabs<De>
                value={de}
                onChange={setDe}
                items={[
                  { value: 'mim', label: 'Minhas' },
                  { value: 'todos', label: 'Da equipe' },
                ]}
              />
            )}
          </>
        }
      />
      {aba === 'opiniao' && <SegundaOpiniao />}
      {aba === 'regras' && <Regras podeEscrever={can('diagnosis:review')} />}
      {aba === 'painel' && <ErrorBox error={q.error} className="mb-4" />}
      {aba === 'painel' && q.isLoading && <Spinner />}
      {aba === 'painel' && d && d.licoes === 0 && (
        <Card>
          <Empty title="Nenhuma lição ainda" icon={<GraduationCap className="size-5" />}>
            Revise um caso na fila do agrônomo: escolha o diagnóstico, diga por quê e arraste sobre a foto para marcar a lesão.
          </Empty>
        </Card>
      )}
      {aba === 'painel' && d && d.licoes > 0 && (
        <div className="flex flex-col gap-4">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Stat
              label="Lições"
              value={<span className="num">{d.licoes}</span>}
              hint={
                d.confiabilidade?.indice != null
                  ? `concorda com colegas: ${fmt.percent(d.confiabilidade.indice)} (${d.confiabilidade.pares} pares)`
                  : 'sem segunda opinião ainda'
              }
            />
            <Stat
              label="Com o porquê"
              value={<span className="num">{d.com_porque}</span>}
              hint={fmt.percent(d.com_porque / d.licoes)}
            />
            <Stat
              label="Lesões marcadas"
              value={<span className="num">{d.lesoes_marcadas}</span>}
              hint={`em ${d.com_lesao_marcada} foto(s)`}
            />
            <Stat
              label="Acerto da IA nos seus casos"
              value={<span className="num">{d.acerto_da_ia_por_mes.length ? fmt.percent(d.acerto_da_ia_por_mes[d.acerto_da_ia_por_mes.length - 1]?.taxa ?? 0) : '—'}</span>}
              hint={t == null ? 'tendência com mais meses' : `${t >= 0 ? '+' : ''}${fmt.number(t * 100, 1)} pontos desde o 1º mês`}
            />
          </div>

          <div className="grid gap-4 xl:grid-cols-2">
            <Card>
              <CardHeader title="Onde a IA mais erra com você" subtitle="O que ela dizia e o que você disse. É onde cada lição rende mais." />
              {d.onde_a_ia_mais_erra.length === 0 ? (
                <Empty title="Ela concordou com você em tudo">Quando discordar, o par aparece aqui.</Empty>
              ) : (
                <Table>
                  <thead>
                    <tr>
                      <th className={th}>A IA dizia</th>
                      <th className={th}>Você disse</th>
                      <th className={th}>Vezes</th>
                    </tr>
                  </thead>
                  <tbody>
                    {d.onde_a_ia_mais_erra.map((c) => (
                      <tr key={`${c.ia_dizia}-${c.voce_disse}`}>
                        <td className={td}>{disease(c.ia_dizia)}</td>
                        <td className={td}>{disease(c.voce_disse)}</td>
                        <td className={`${td} num`}>{c.vezes}</td>
                      </tr>
                    ))}
                  </tbody>
                </Table>
              )}
            </Card>

            <Card>
              <CardHeader title="Acerto da IA mês a mês" subtitle={d.vies} />
              <div className="flex flex-col gap-3 px-5 pb-5 text-[13px]">
                {d.acerto_da_ia_por_mes.map((m) => (
                  <div key={m.mes}>
                    <div className="mb-1 flex justify-between">
                      <span>{m.mes}</span>
                      <span className="num text-muted">
                        {m.ia_acertou}/{m.casos} · {fmt.percent(m.taxa)}
                      </span>
                    </div>
                    <Meter value={m.taxa} tone={m.taxa >= 0.8 ? 'good' : m.taxa >= 0.5 ? 'warning' : 'critical'} label={`Acerto em ${m.mes}`} />
                  </div>
                ))}
                {d.acerto_da_ia_por_mes.length === 0 && <span className="text-muted">Sem caso da fila ainda.</span>}
              </div>
            </Card>
          </div>

          {d.classes_novas.length > 0 && (
            <Card>
              <CardHeader
                title="Doenças novas que você está ensinando"
                subtitle={`O modelo ainda não tem estas classes. Com ${d.alvo_por_classe_nova} exemplos confirmados, a equipe consegue treinar a IA para reconhecê-las.`}
              />
              <div className="flex flex-col gap-3 px-5 pb-5 text-[13px]">
                {d.classes_novas.map((c) => (
                  <div key={c.rotulo}>
                    <div className="mb-1 flex justify-between">
                      <span className="font-medium">{disease(c.rotulo)}</span>
                      <span className="num text-muted">
                        {c.exemplos} exemplo(s){c.faltam > 0 ? ` · faltam ${c.faltam}` : ' · pronto para treinar'}
                      </span>
                    </div>
                    <Meter value={Math.min(1, c.exemplos / d.alvo_por_classe_nova)} tone={c.faltam ? 'accent' : 'good'} label={c.rotulo} />
                  </div>
                ))}
              </div>
            </Card>
          )}

          <Card className="overflow-hidden p-0">
            <CardHeader title="Últimas lições" />
            <Table>
              <thead>
                <tr>
                  <th className={th}>Quando</th>
                  <th className={th}>Diagnóstico</th>
                  <th className={th}>A IA dizia</th>
                  <th className={th}>Por quê</th>
                  <th className={th}>Lesões</th>
                </tr>
              </thead>
              <tbody>
                {d.ultimas.map((x) => (
                  <tr key={x.id}>
                    <td className={`${td} text-[12px]`}>
                      {fmt.dateTime(x.quando)}
                      <div className="text-muted">
                        {x.origem === 'parecer' ? 'discordando do parecer' : 'fila'}
                        {de === 'todos' ? ` · ${x.autor}` : ''}
                      </div>
                    </td>
                    <td className={td}>{disease(x.rotulo)}</td>
                    <td className={td}>{x.rotulo_da_ia ? disease(x.rotulo_da_ia) : '—'}</td>
                    <td className={`${td} text-[12px]`}>
                      {x.sintomas.length > 0 && (
                        <div className="mb-1 flex flex-wrap gap-1">
                          {x.sintomas.map((s) => (
                            <Badge key={s} tone="neutral">
                              {s}
                            </Badge>
                          ))}
                        </div>
                      )}
                      {x.porque ?? (x.sintomas.length ? '' : '—')}
                    </td>
                    <td className={`${td} num`}>{x.lesoes}</td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </Card>
        </div>
      )}
    </>
  )
}
