import { Building2, MapPin, Plus, Search } from 'lucide-react'
import { useMemo, useState } from 'react'

import { useAdminTenants, useOnboardTenant } from '@/api/queries'
import type { OnboardIn, TenantOut } from '@/api/types'
import { FarmMap } from '@/components/FarmMap'
import {
  Badge,
  Button,
  Card,
  CardHeader,
  Empty,
  ErrorBox,
  FormField,
  Modal,
  PageHeader,
  Spinner,
  Table,
  td,
  th,
  useToast,
} from '@/components/ui'
import { fmt } from '@/lib/format'
import { parseCoords } from '@/lib/geo'

/**
 * Cadastrar cliente.
 *
 * O formulário existe porque hoje um cliente novo entra por `seed` ou por
 * inserção manual no banco, e nenhuma das duas deixa rastro de quem o criou.
 *
 * Três decisões de tela:
 *
 * **Quase tudo é opcional.** O cadastro começa numa ligação, com o nome e o
 * telefone. Exigir endereço completo faria quem atende inventar um — e endereço
 * inventado é pior que campo vazio, porque parece preenchido e ninguém volta
 * para conferir.
 *
 * **As coordenadas se colam, não se digitam.** Ninguém sabe de cor onde fica a
 * fazenda; todo mundo tem o ponto aberto no Google Maps. O campo aceita o
 * formato de lá — inclusive com vírgula decimal — e o mapa confirma na hora se
 * o ponto caiu no lugar certo.
 *
 * **O contorno do talhão não é pedido aqui.** Ele se desenha no editor, com a
 * imagem de satélite na frente. Pedi-lo ao telefone renderia um polígono
 * inventado, e o polígono é a cerca virtual de toda missão.
 */
export default function Tenants() {
  const clientes = useAdminTenants()
  const [busca, setBusca] = useState('')
  const [abrindo, setAbrindo] = useState(false)

  const lista = useMemo(() => {
    const termo = busca.trim().toLowerCase()
    const linhas = clientes.data ?? []
    if (!termo) return linhas
    return linhas.filter((item) =>
      [item.name, item.slug, item.document, item.city, item.contact_name]
        .filter(Boolean)
        .some((campo) => String(campo).toLowerCase().includes(termo)),
    )
  }, [clientes.data, busca])

  return (
    <>
      <PageHeader
        title="Clientes"
        subtitle="Quem contrata a ValTexa. Cada um enxerga apenas a própria lavoura."
        actions={
          <Button onClick={() => setAbrindo(true)}>
            <Plus className="size-4" aria-hidden />
            Cadastrar cliente
          </Button>
        }
      />

      <ErrorBox error={clientes.error} className="mb-3" />

      <Card>
        <CardHeader
          title={`${lista.length} cliente(s)`}
          actions={
            <label className="relative">
              <Search
                className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted"
                aria-hidden
              />
              <input
                className="input h-8 w-56 pl-8 text-[13px]"
                placeholder="Nome, documento, cidade"
                value={busca}
                onChange={(evento) => setBusca(evento.target.value)}
              />
            </label>
          }
        />
        {clientes.isLoading ? (
          <Spinner label="Carregando clientes" />
        ) : lista.length === 0 ? (
          <Empty title={busca ? 'Nenhum cliente com esse termo' : 'Nenhum cliente ainda'}>
            {busca
              ? 'Tente outro nome, documento ou cidade.'
              : 'Cadastre o primeiro para começar a importar coletas.'}
          </Empty>
        ) : (
          <Table>
            <thead>
              <tr>
                <th className={th}>Cliente</th>
                <th className={th}>Documento</th>
                <th className={th}>Contato</th>
                <th className={th}>Cidade</th>
                <th className={th}>Serviço</th>
                <th className={th}>Operação</th>
              </tr>
            </thead>
            <tbody>
              {lista.map((cliente) => (
                <LinhaDeCliente key={cliente.id} cliente={cliente} />
              ))}
            </tbody>
          </Table>
        )}
      </Card>

      {abrindo && <FormularioDeCadastro onFechar={() => setAbrindo(false)} />}
    </>
  )
}

function LinhaDeCliente({ cliente }: { cliente: TenantOut }) {
  return (
    <tr>
      <td className={td}>
        <div className="font-medium">{cliente.name}</div>
        <div className="text-[12px] text-muted">{cliente.slug}</div>
      </td>
      <td className={`${td} num`}>{cliente.document ?? '—'}</td>
      <td className={td}>
        {cliente.contact_name ?? '—'}
        {cliente.phone && <div className="num text-[12px] text-muted">{cliente.phone}</div>}
      </td>
      <td className={td}>
        {cliente.city ? `${cliente.city}${cliente.state ? `/${cliente.state}` : ''}` : '—'}
      </td>
      <td className={td}>
        {cliente.contracted_service ? (
          <span className="text-[13px]">{cliente.contracted_service}</span>
        ) : (
          <span className="text-muted">—</span>
        )}
      </td>
      <td className={td}>
        <div className="flex flex-wrap items-center gap-1.5">
          <Badge tone="neutral">{cliente.farms} propriedade(s)</Badge>
          <Badge tone="neutral">{cliente.fields} talhão(ões)</Badge>
          {cliente.area_ha ? <Badge tone="info">{fmt.hectares(cliente.area_ha)}</Badge> : null}
        </div>
      </td>
    </tr>
  )
}

/** Gera um apelido a partir do nome: é a identidade pública e não muda depois. */
function apelidoDe(nome: string): string {
  return nome
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 64)
}

const VAZIO = {
  name: '',
  slug: '',
  document: '',
  contact_name: '',
  email: '',
  phone: '',
  address: '',
  city: '',
  state: '',
  postal_code: '',
  contracted_service: '',
  notes: '',
  farm_name: '',
  farm_area: '',
  field_name: '',
  crop: 'coffee',
  variety: '',
  row_spacing: '',
}

function FormularioDeCadastro({ onFechar }: { onFechar: () => void }) {
  const cadastrar = useOnboardTenant()
  const toast = useToast()
  const [form, setForm] = useState({ ...VAZIO })
  const [apelidoManual, setApelidoManual] = useState(false)
  const [coordenadas, setCoordenadas] = useState('')
  const [ponto, setPonto] = useState<[number, number] | null>(null)
  const [recado, setRecado] = useState<string | null>(null)

  const definir = (campo: keyof typeof VAZIO) => (valor: string) =>
    setForm((atual) => ({ ...atual, [campo]: valor }))

  const apelido = apelidoManual ? form.slug : apelidoDe(form.name)
  const podeSalvar = form.name.trim().length >= 2 && apelido.length >= 2

  function aplicarCoordenadas() {
    const { points, aviso } = parseCoords(coordenadas)
    const primeiro = points[0]
    if (!primeiro) {
      setRecado(aviso ?? 'Cole a coordenada do Google Maps: latitude, longitude.')
      return
    }
    const [lon = 0, lat = 0] = primeiro
    setPonto([lat, lon])
    setRecado(
      points.length > 1
        ? `Usei o primeiro de ${points.length} pontos: ${lat.toFixed(5)}, ${lon.toFixed(5)}.`
        : `${lat.toFixed(5)}, ${lon.toFixed(5)}. Confira no mapa antes de salvar.`,
    )
  }

  async function salvar() {
    const corpo: OnboardIn = {
      tenant: {
        name: form.name.trim(),
        slug: apelido,
        document: form.document.trim() || null,
        contact_name: form.contact_name.trim() || null,
        email: form.email.trim() || null,
        phone: form.phone.trim() || null,
        address: form.address.trim() || null,
        city: form.city.trim() || null,
        state: form.state.trim().toUpperCase() || null,
        postal_code: form.postal_code.trim() || null,
        contracted_service: form.contracted_service.trim() || null,
        notes: form.notes.trim() || null,
      },
      farm:
        form.farm_name.trim() && ponto
          ? {
              name: form.farm_name.trim(),
              center_lat: ponto[0],
              center_lon: ponto[1],
              area_ha: Number(form.farm_area) || null,
              timezone: 'America/Sao_Paulo',
            }
          : null,
      field:
        form.farm_name.trim() && ponto && form.field_name.trim()
          ? {
              name: form.field_name.trim(),
              crop: form.crop,
              variety: form.variety.trim() || null,
              row_spacing_m: Number(form.row_spacing) || null,
              // O contorno vem depois, no editor, com satélite na frente.
              boundary: [],
            }
          : null,
    }

    const resultado = await cadastrar.mutateAsync(corpo)
    const avisos = resultado.warnings ?? []
    toast.push({
      tone: avisos.length ? 'warning' : 'good',
      title: `${resultado.tenant.name} cadastrado.`,
      detail: avisos[0],
    })
    onFechar()
  }

  return (
    <Modal
      open
      onClose={onFechar}
      title="Cadastrar cliente"
      wide
      footer={
        <>
          <Button variant="ghost" onClick={onFechar}>
            Cancelar
          </Button>
          <Button disabled={!podeSalvar || cadastrar.isPending} onClick={salvar}>
            {cadastrar.isPending ? 'Salvando…' : 'Cadastrar'}
          </Button>
        </>
      }
    >
      <div className="space-y-5">
        <ErrorBox error={cadastrar.error} />

        <section className="space-y-3">
          <h3 className="flex items-center gap-2 text-[13px] font-medium">
            <Building2 className="size-4" aria-hidden />
            Identificação
          </h3>
          <div className="grid gap-3 sm:grid-cols-2">
            <FormField label="Nome ou razão social">
              <input
                className="input"
                value={form.name}
                onChange={(evento) => definir('name')(evento.target.value)}
                placeholder="Fazenda São João Agropecuária Ltda"
              />
            </FormField>
            <FormField
              label="Apelido"
              hint="Identidade pública do cliente. Não muda depois de criado."
            >
              <input
                className="input font-mono text-[13px]"
                value={apelido}
                onChange={(evento) => {
                  setApelidoManual(true)
                  definir('slug')(apelidoDe(evento.target.value))
                }}
              />
            </FormField>
            <FormField label="CPF / CNPJ">
              <input
                className="input num"
                value={form.document}
                onChange={(evento) => definir('document')(evento.target.value)}
                placeholder="12.345.678/0001-90"
              />
            </FormField>
            <FormField label="Serviço contratado">
              <input
                className="input"
                value={form.contracted_service}
                onChange={(evento) => definir('contracted_service')(evento.target.value)}
                placeholder="Monitoramento com rover"
              />
            </FormField>
          </div>
        </section>

        <section className="space-y-3">
          <h3 className="text-[13px] font-medium">Contato</h3>
          <div className="grid gap-3 sm:grid-cols-2">
            <FormField label="Responsável">
              <input
                className="input"
                value={form.contact_name}
                onChange={(evento) => definir('contact_name')(evento.target.value)}
              />
            </FormField>
            <FormField label="Telefone">
              <input
                className="input num"
                value={form.phone}
                onChange={(evento) => definir('phone')(evento.target.value)}
                placeholder="(35) 99999-0000"
              />
            </FormField>
            <FormField label="E-mail">
              <input
                className="input"
                type="email"
                value={form.email}
                onChange={(evento) => definir('email')(evento.target.value)}
              />
            </FormField>
            <FormField label="Endereço">
              <input
                className="input"
                value={form.address}
                onChange={(evento) => definir('address')(evento.target.value)}
                placeholder="Rodovia MG-290, km 12"
              />
            </FormField>
            <div className="grid grid-cols-[1fr_5rem_7rem] gap-2">
              <FormField label="Cidade">
                <input
                  className="input"
                  value={form.city}
                  onChange={(evento) => definir('city')(evento.target.value)}
                />
              </FormField>
              <FormField label="UF">
                <input
                  className="input uppercase"
                  maxLength={2}
                  value={form.state}
                  onChange={(evento) => definir('state')(evento.target.value)}
                />
              </FormField>
              <FormField label="CEP">
                <input
                  className="input num"
                  value={form.postal_code}
                  onChange={(evento) => definir('postal_code')(evento.target.value)}
                />
              </FormField>
            </div>
          </div>
        </section>

        <section className="space-y-3 border-t border-line-soft pt-4">
          <h3 className="flex items-center gap-2 text-[13px] font-medium">
            <MapPin className="size-4" aria-hidden />
            Propriedade
            <span className="font-normal text-muted">opcional — dá para cadastrar depois</span>
          </h3>
          <div className="grid gap-3 sm:grid-cols-2">
            <FormField label="Nome da propriedade">
              <input
                className="input"
                value={form.farm_name}
                onChange={(evento) => definir('farm_name')(evento.target.value)}
                placeholder="Sítio Boa Vista"
              />
            </FormField>
            <FormField label="Área total (ha)">
              <input
                className="input num"
                inputMode="decimal"
                value={form.farm_area}
                onChange={(evento) => definir('farm_area')(evento.target.value)}
              />
            </FormField>
          </div>

          <FormField
            label="Coordenadas"
            hint="Cole do Google Maps: clique no ponto, copie o par de números e cole aqui."
          >
            <div className="flex gap-2">
              <input
                className="input font-mono text-[13px]"
                value={coordenadas}
                onChange={(evento) => setCoordenadas(evento.target.value)}
                placeholder="-21.90400, -45.86200"
              />
              <Button variant="secondary" onClick={aplicarCoordenadas}>
                Localizar
              </Button>
            </div>
          </FormField>
          {recado && <p className="text-[12px] text-ink-2">{recado}</p>}

          {ponto && (
            <FarmMap className="h-56" focus={ponto} focusZoom={15} draftPolygon={[]} />
          )}

          <div className="grid gap-3 sm:grid-cols-2">
            <FormField
              label="Primeiro talhão"
              hint="O contorno se desenha depois, no editor, com satélite na frente."
            >
              <input
                className="input"
                value={form.field_name}
                onChange={(evento) => definir('field_name')(evento.target.value)}
                placeholder="Talhão A"
              />
            </FormField>
            <FormField label="Cultura">
              <select
                className="input"
                value={form.crop}
                onChange={(evento) => definir('crop')(evento.target.value)}
              >
                <option value="coffee">Café</option>
                <option value="corn">Milho</option>
                <option value="soy">Soja</option>
              </select>
            </FormField>
            <FormField label="Variedade">
              <input
                className="input"
                value={form.variety}
                onChange={(evento) => definir('variety')(evento.target.value)}
                placeholder="Catuaí Vermelho IAC 144"
              />
            </FormField>
            <FormField label="Espaçamento entre linhas (m)">
              <input
                className="input num"
                inputMode="decimal"
                value={form.row_spacing}
                onChange={(evento) => definir('row_spacing')(evento.target.value)}
                placeholder="3.5"
              />
            </FormField>
          </div>
          {form.farm_name.trim() && !ponto && (
            <p className="text-[12px] text-warning">
              A propriedade precisa de coordenadas para ser criada. Sem elas, só o cliente é
              cadastrado.
            </p>
          )}
        </section>

        {ponto && form.field_name.trim() && (
          <p className="text-[12px] text-muted">
            O talhão nasce sem polígono. Depois de salvar, abra-o em Talhões e desenhe o
            contorno — é ele que vira a cerca virtual de toda missão.
          </p>
        )}
      </div>
    </Modal>
  )
}
