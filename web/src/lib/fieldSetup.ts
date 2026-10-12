/**
 * Regras do cadastro do talhão que a tela aplica antes de chamar o servidor
 * (que confere de novo — ver `FieldCreate`/`FieldUpdate` em `saas/valtexa/schemas.py`).
 */

export type RowsParse = { rows: number[]; error: string | null }

/**
 * Lê as fileiras de validação como o agrônomo escreve: "3, 10, 17" ou "3-5, 12".
 * Devolve em ordem, sem repetição — a mesma regra do servidor.
 */
export function parseValidationRows(text: string, rowCount?: number | null): RowsParse {
  const rows: number[] = []
  const limpo = text.trim()
  if (!limpo) return { rows, error: null }
  for (const parte of limpo.split(/[,;\s]+/).filter(Boolean)) {
    const faixa = /^(\d+)\s*-\s*(\d+)$/.exec(parte)
    if (faixa) {
      const inicio = Number(faixa[1])
      const fim = Number(faixa[2])
      if (inicio < 1 || fim < inicio) return { rows: [], error: `Faixa inválida: ${parte}.` }
      if (fim - inicio > 500) return { rows: [], error: `Faixa grande demais: ${parte}.` }
      for (let linha = inicio; linha <= fim; linha += 1) rows.push(linha)
    } else if (/^\d+$/.test(parte)) {
      const linha = Number(parte)
      if (linha < 1) return { rows: [], error: 'A linha começa em 1.' }
      rows.push(linha)
    } else {
      return { rows: [], error: `Não entendi “${parte}”. Use números, vírgulas e faixas como 3-5.` }
    }
  }
  const unicas = [...new Set(rows)].sort((a, b) => a - b)
  if (unicas.length > 500) return { rows: [], error: 'No máximo 500 fileiras de validação.' }
  if (rowCount && unicas.some((linha) => linha > rowCount)) {
    return { rows: [], error: `O talhão tem ${rowCount} linhas: a fileira ${unicas.at(-1)} não existe.` }
  }
  return { rows: unicas, error: null }
}

/** Escreve as fileiras de volta, compactando sequências: [3,4,5,9] → "3-5, 9". */
export function formatValidationRows(rows: readonly number[]): string {
  const partes: string[] = []
  let inicio: number | null = null
  let anterior: number | null = null
  for (const linha of [...rows].sort((a, b) => a - b)) {
    if (inicio === null) {
      inicio = linha
    } else if (linha !== (anterior ?? 0) + 1) {
      partes.push(inicio === anterior ? `${inicio}` : `${inicio}-${anterior}`)
      inicio = linha
    }
    anterior = linha
  }
  if (inicio !== null) partes.push(inicio === anterior ? `${inicio}` : `${inicio}-${anterior}`)
  return partes.join(', ')
}

/** Número opcional de um campo de texto: vazio vira nulo; inválido também. */
export function optionalNumber(text: string): number | null {
  const valor = Number(text.replace(',', '.'))
  return text.trim() === '' || !Number.isFinite(valor) ? null : valor
}

type FieldLike = {
  boundary?: unknown[] | null
  row_spacing_m?: number | null
  plant_spacing_m?: number | null
  row_azimuth_deg?: number | null
  row_count?: number | null
  validation_rows?: readonly number[] | null
}

export type SetupGap = { key: string; message: string; action: string }

/**
 * O que falta no cadastro do talhão, cada item com a próxima ação — o estado
 * vazio que diz o que fazer, não só que está vazio.
 */
export function fieldSetupGaps(field: FieldLike): SetupGap[] {
  const faltas: SetupGap[] = []
  if (!field.boundary || field.boundary.length < 3) {
    faltas.push({
      key: 'contorno',
      message: 'Sem contorno não há área, rota nem cerca virtual.',
      action: 'Desenhar o contorno',
    })
  }
  if (!field.row_spacing_m || !field.plant_spacing_m) {
    faltas.push({
      key: 'espacamento',
      message:
        'Sem os espaçamentos entre linhas e entre plantas, a fusão por planta usa valores padrão — e pode juntar duas plantas numa só.',
      action: 'Informar os espaçamentos',
    })
  }
  if (field.row_azimuth_deg === null || field.row_azimuth_deg === undefined) {
    faltas.push({
      key: 'direcao',
      message: 'Sem a direção das linhas, o planejamento não alinha as passadas às ruas.',
      action: 'Informar a direção das linhas',
    })
  }
  if (!field.validation_rows || field.validation_rows.length === 0) {
    faltas.push({
      key: 'validacao',
      message: 'Sem fileiras de validação, não há como medir a precisão da IA neste talhão.',
      action: 'Escolher as fileiras de validação',
    })
  }
  return faltas
}
