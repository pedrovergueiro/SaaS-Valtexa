import { Check, Ruler, X } from 'lucide-react'
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'

import { api } from '@/api/client'
import { useApiMutation } from '@/api/queries'
import { AuthImage } from '@/components/AuthImage'
import { Badge, Button, Card, CardHeader, Empty, ErrorBox, FormField, Spinner } from '@/components/ui'
import { condicaoDoFormulario, tomDoVeredito, type Pendente, type Regra, type RegraForm } from '@/lib/ensino'
import { disease, KNOWN_LABELS } from '@/lib/labels'

/** Lições de colegas à espera de segunda opinião: confirmar ou corrigir. */
export function SegundaOpiniao() {
  const chave = ['ensino', 'segunda-opiniao']
  const q = useQuery({ queryKey: chave, queryFn: () => api<Pendente[]>('/v1/ensino/segunda-opiniao') })
  if (q.isLoading) return <Spinner />
  if (q.error) return <ErrorBox error={q.error} />
  const itens = q.data ?? []
  if (itens.length === 0) {
    return (
      <Card>
        <Empty title="Nada esperando a sua opinião">Quando um colega ensinar a IA, a lição dele aparece aqui para você confirmar ou corrigir.</Empty>
      </Card>
    )
  }
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      {itens.map((x) => (
        <CartaoDeOpiniao key={x.amostra_id} item={x} chave={chave} />
      ))}
    </div>
  )
}

function CartaoDeOpiniao({ item, chave }: { item: Pendente; chave: string[] }) {
  const [outro, setOutro] = useState('')
  const opinar = useApiMutation(
    (rotulo: string) => api(`/v1/ensino/segunda-opiniao/${item.amostra_id}`, { method: 'POST', body: { rotulo } }),
    [chave, ['ensino', 'painel']],
  )
  const valido = /^[A-Za-z][A-Za-z0-9_]{0,63}$/.test(outro)
  return (
    <Card className="overflow-hidden">
      {item.observation_id && <AuthImage path={`/v1/observations/${item.observation_id}/image`} alt="Foto da lição" className="aspect-[4/3] w-full" />}
      <div className="flex flex-col gap-2 p-4 text-[13px]">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-medium">{disease(item.rotulo)}</span>
          <span className="text-muted">por {item.autor ?? 'colega'}</span>
          {item.em_disputa && <Badge tone="warning">em disputa</Badge>}
          {item.lesoes.length > 0 && <Badge tone="neutral">{item.lesoes.length} lesão(ões) marcada(s)</Badge>}
        </div>
        {item.sintomas.length > 0 && <div className="text-ink-2">Viu: {item.sintomas.join('; ')}</div>}
        {item.porque && <div className="text-ink-2">“{item.porque}”</div>}
        <ErrorBox error={opinar.error} />
        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" variant="primary" icon={<Check className="size-4" />} loading={opinar.isPending} onClick={() => opinar.mutate(item.rotulo)}>
            Concordo
          </Button>
          <input
            className="input w-48"
            list="rotulos-opiniao"
            placeholder="Ou: o que é?"
            value={outro}
            onChange={(e) => setOutro(e.target.value.replaceAll(' ', '_'))}
          />
          <Button size="sm" icon={<X className="size-4" />} disabled={!valido || outro === item.rotulo} onClick={() => opinar.mutate(outro)}>
            Discordo
          </Button>
        </div>
        <datalist id="rotulos-opiniao">
          {KNOWN_LABELS.map((v) => (
            <option key={v} value={v}>
              {disease(v)}
            </option>
          ))}
        </datalist>
      </div>
    </Card>
  )
}

const VAZIA: RegraForm = { cultura: 'coffee', doenca: 'Leaf_Miner_Damage', texto: '', variavel: 'chuva_mm', janela: '14', operador: '<', valor: '10', meses: '6,7,8', efeito: 'aumenta' }

/** O que o agrônomo sabe, escrito como regra e medido no histórico do cliente. */
export function Regras({ podeEscrever }: { podeEscrever: boolean }) {
  const chave = ['ensino', 'regras']
  const q = useQuery({ queryKey: chave, queryFn: () => api<Regra[]>('/v1/ensino/regras') })
  const [form, setForm] = useState<RegraForm>(VAZIA)
  const criar = useApiMutation(
    () =>
      api('/v1/ensino/regras', {
        method: 'POST',
        body: { cultura: form.cultura, doenca: form.doenca, texto: form.texto, efeito: form.efeito, condicao: condicaoDoFormulario(form) },
      }),
    [chave],
  )
  const medir = useApiMutation((id: string) => api(`/v1/ensino/regras/${id}/medir`, { method: 'POST' }), [chave])
  const ativar = useApiMutation(
    ({ id, ativa }: { id: string; ativa: boolean }) => api(`/v1/ensino/regras/${id}/ativa`, { method: 'POST', query: { ativa } }),
    [chave],
  )
  const muda = (k: keyof RegraForm) => (e: { target: { value: string } }) => setForm({ ...form, [k]: e.target.value })
  return (
    <div className="flex flex-col gap-4">
      {podeEscrever && (
        <Card>
          <CardHeader
            title="Escrever uma regra"
            subtitle="Ex.: 'bicho-mineiro sobe na seca' = chuva acumulada em 14 dias abaixo de 10 mm aumenta bicho-mineiro. A plataforma mede no histórico; o parecer cita a regra com o resultado da medida."
          />
          <div className="grid gap-3 px-5 pb-5 md:grid-cols-3">
            <FormField label="A regra, nas suas palavras">
              <input className="input" value={form.texto} onChange={muda('texto')} maxLength={1000} placeholder="bicho-mineiro sobe na seca" />
            </FormField>
            <FormField label="Doença">
              <input className="input font-mono" list="rotulos-regra" value={form.doenca} onChange={muda('doenca')} />
            </FormField>
            <FormField label="Cultura">
              <input className="input" value={form.cultura} onChange={muda('cultura')} />
            </FormField>
            <FormField label="Condição">
              <select className="input" value={form.variavel} onChange={muda('variavel')}>
                <option value="chuva_mm">Chuva acumulada (mm)</option>
                <option value="molhamento_h">Horas de folha molhada</option>
                <option value="ur_media">Umidade média (%)</option>
                <option value="t_media">Temperatura média (°C)</option>
                <option value="mes">Meses do ano</option>
              </select>
            </FormField>
            {form.variavel === 'mes' ? (
              <FormField label="Meses" hint="Ex.: 6,7,8">
                <input className="input" value={form.meses} onChange={muda('meses')} />
              </FormField>
            ) : (
              <FormField label="Nos últimos (dias) · operador · valor">
                <div className="flex gap-2">
                  <input className="input w-20" inputMode="numeric" value={form.janela} onChange={muda('janela')} />
                  <select className="input w-20" value={form.operador} onChange={muda('operador')}>
                    <option value="<">abaixo de</option>
                    <option value=">">acima de</option>
                  </select>
                  <input className="input w-24" inputMode="decimal" value={form.valor} onChange={muda('valor')} />
                </div>
              </FormField>
            )}
            <FormField label="Efeito">
              <select className="input" value={form.efeito} onChange={muda('efeito')}>
                <option value="aumenta">aumenta a doença</option>
                <option value="diminui">diminui a doença</option>
              </select>
            </FormField>
            <div className="md:col-span-3">
              <ErrorBox error={criar.error} className="mb-2" />
              <Button
                variant="primary"
                disabled={form.texto.trim().length < 5}
                loading={criar.isPending}
                onClick={() => criar.mutate(undefined, { onSuccess: () => setForm(VAZIA) })}
              >
                Guardar a regra
              </Button>
            </div>
          </div>
          <datalist id="rotulos-regra">
            {KNOWN_LABELS.map((v) => (
              <option key={v} value={v}>
                {disease(v)}
              </option>
            ))}
          </datalist>
        </Card>
      )}
      <ErrorBox error={q.error ?? medir.error ?? ativar.error} />
      {q.isLoading && <Spinner />}
      {(q.data ?? []).length === 0 && !q.isLoading && (
        <Card>
          <Empty title="Nenhuma regra ainda">Escreva o que você sabe; a plataforma mede se o histórico concorda.</Empty>
        </Card>
      )}
      {(q.data ?? []).map((r) => (
        <Card key={r.id} className="p-4 text-[13px]">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-medium">“{r.texto}”</span>
            <Badge tone={tomDoVeredito(r.medida.veredito)}>{r.veredito_texto}</Badge>
            {!r.ativa && <Badge tone="neutral">desligada</Badge>}
          </div>
          <div className="mt-1 text-muted">
            {r.condicao_texto} {r.efeito} {disease(r.doenca)} · {r.autor}
          </div>
          {r.medida.com_condicao && r.medida.sem_condicao && (
            <div className="num mt-1 text-[12px] text-muted">
              Com a condição: {r.medida.com_condicao.com_doenca} de {r.medida.com_condicao.casos} casos · sem: {r.medida.sem_condicao.com_doenca} de{' '}
              {r.medida.sem_condicao.casos}
              {r.medida.p_valor != null ? ` · p = ${r.medida.p_valor}` : ''}
            </div>
          )}
          {podeEscrever && (
            <div className="mt-2 flex gap-2">
              <Button size="sm" icon={<Ruler className="size-4" />} loading={medir.isPending} onClick={() => medir.mutate(r.id)}>
                Medir no histórico
              </Button>
              <Button size="sm" variant="ghost" onClick={() => ativar.mutate({ id: r.id, ativa: !r.ativa })}>
                {r.ativa ? 'Tirar dos pareceres' : 'Voltar aos pareceres'}
              </Button>
            </div>
          )}
        </Card>
      ))}
    </div>
  )
}
