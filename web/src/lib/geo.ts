/**
 * Área de polígono no navegador — a mesma aproximação local de
 * `valtexa/services/geo.py`, só para mostrar ao usuário enquanto ele desenha.
 * O número que vale é o que o servidor calcula ao gravar.
 */
const METERS_PER_DEGREE_LAT = 111_320

export function areaHa(ring: number[][]): number {
  if (ring.length < 3) return 0
  const lat0 = ring.reduce((sum, point) => sum + (point[1] ?? 0), 0) / ring.length
  const scaleLon = METERS_PER_DEGREE_LAT * Math.cos((lat0 * Math.PI) / 180)
  let total = 0
  for (let index = 0; index < ring.length; index += 1) {
    const a = ring[index] ?? [0, 0]
    const b = ring[(index + 1) % ring.length] ?? [0, 0]
    total += (a[0] ?? 0) * scaleLon * ((b[1] ?? 0) * METERS_PER_DEGREE_LAT) - (b[0] ?? 0) * scaleLon * ((a[1] ?? 0) * METERS_PER_DEGREE_LAT)
  }
  return Math.abs(total) / 2 / 10_000
}

/**
 * Lê coordenadas coladas pelo produtor, em qualquer dos formatos que ele tem
 * à mão.
 *
 * O texto vem do Google Maps, de um GPS de mão, de um KML aberto no bloco de
 * notas ou de um e-mail do agrimensor. Exigir um formato só faria a pessoa
 * editar o texto à mão — e é aí que nasce um vértice errado que ninguém nota
 * até o rover ir para o lugar errado.
 *
 * Aceita, por linha ou separados por ponto e vírgula:
 *
 * - `-21.9040, -45.8620`      (Google Maps: latitude primeiro)
 * - `-21.9040 -45.8620`
 * - `-21,9040; -45,8620`      (vírgula decimal, como o Excel brasileiro exporta)
 * - `[-45.8620, -21.9040]`    (GeoJSON: longitude primeiro)
 *
 * Devolve sempre `[lon, lat]`, que é a ordem do resto da plataforma.
 */
export type ParsedCoords = {
  points: number[][]
  /** O que a leitura entendeu, para a pessoa conferir antes de aplicar. */
  aviso: string | null
}

export function parseCoords(texto: string): ParsedCoords {
  const bruto = texto.trim()
  if (!bruto) return { points: [], aviso: null }

  // GeoJSON colado inteiro: aproveita o anel de coordenadas e evita adivinhação.
  if (bruto.startsWith('{') || bruto.startsWith('[')) {
    const doGeoJson = anelDeGeoJson(bruto)
    if (doGeoJson) return { points: doGeoJson, aviso: 'Lido como GeoJSON (longitude, latitude).' }
  }

  // Graus, minutos e segundos — o formato que o Google Maps mostra no painel do
  // lugar, antes de você pedir o decimal. Precisa vir antes da leitura numérica
  // comum, e não depois: `21°54'14.4"S` tem três números, e a leitura comum
  // pegaria os dois primeiros (21 e 54) como se fossem latitude e longitude.
  // O ponto cairia no Sudão, com um aviso que ninguém lê — o erro silencioso
  // que manda o rover para o lugar errado.
  const emGraus = parseDMS(bruto)
  if (emGraus) return emGraus

  // Uma linha pode trazer um par ou vários; o que separa os pontos entre si
  // (vírgula, ponto e vírgula, espaço) é o mesmo que separa latitude de
  // longitude, então tratar o separador como estrutura não funciona. O que
  // funciona é ler todos os números da linha e agrupá-los de dois em dois.
  //
  // Antes isto quebrava `-21,9029; -45,8624`: o ponto e vírgula partia o par em
  // duas linhas de um número cada, as duas eram descartadas, e o produtor que
  // colasse a exportação do Excel brasileiro não recebia ponto nenhum.
  const numeros = bruto
    .split(/\n+/)
    .flatMap((linha) => {
      const achados = (linha.match(/-?\d+(?:[.,]\d+)?/g) ?? []).map((n) =>
        Number(n.replace(',', '.')),
      )
      const pares: number[][] = []
      for (let i = 0; i + 1 < achados.length; i += 2) {
        pares.push([achados[i] ?? 0, achados[i + 1] ?? 0])
      }
      return pares
    })

  if (!numeros.length) return { points: [], aviso: 'Nenhuma coordenada reconhecida no texto.' }

  // Qual dos dois é latitude? Latitude nunca passa de 90; no Brasil a longitude
  // é sempre menor que -34. Quando os dois números cabem nas duas faixas — o
  // caso de -21 e -45 —, vale a convenção do Google Maps: latitude primeiro.
  const primeiroSoPodeSerLongitude = numeros.some(([a]) => Math.abs(a ?? 0) > 90)
  const segundoSoPodeSerLongitude = numeros.some(([, b]) => Math.abs(b ?? 0) > 90)

  let latPrimeiro = true
  let aviso: string | null = 'Lido como latitude, longitude — a ordem do Google Maps.'
  if (primeiroSoPodeSerLongitude && !segundoSoPodeSerLongitude) {
    latPrimeiro = false
    aviso = 'Lido como longitude, latitude: o primeiro número passa de 90 e só pode ser longitude.'
  }

  const points = numeros.map(([a = 0, b = 0]) => (latPrimeiro ? [b, a] : [a, b]))
  const foraDoBrasil = points.some(
    ([lon = 0, lat = 0]) => lat > 6 || lat < -34 || lon > -33 || lon < -74,
  )
  if (foraDoBrasil) {
    aviso = `${aviso} Atenção: o ponto cai fora do Brasil — confira se a ordem está certa.`
  }
  return { points, aviso }
}

/**
 * Um par em graus, minutos e segundos, com hemisfério pela letra.
 *
 * Casa `21°54'14.4"S`, `21 54 14.4 S`, `21°54.24'S` (sem segundos) e a variante
 * com aspas retas que o Windows produz ao copiar. O hemisfério é obrigatório:
 * é ele que dá o sinal, e sem sinal não há como distinguir sul de norte.
 */
const GRAU = /(\d+(?:[.,]\d+)?)\s*[°º]?\s*(?:(\d+(?:[.,]\d+)?)\s*['′]?\s*)?(?:(\d+(?:[.,]\d+)?)\s*(?:''|["″])?\s*)?([NSEWLO])/giu

function parseDMS(bruto: string): ParsedCoords | null {
  const achados = [...bruto.matchAll(GRAU)]
  if (achados.length < 2) return null

  const decimais = achados.map((achado) => {
    const [, g = '0', m = '0', s = '0', letra = 'N'] = achado
    const num = (valor: string) => Number(valor.replace(',', '.'))
    const magnitude = num(g) + num(m) / 60 + num(s) / 3600
    // S e W (ou O, de Oeste, como o português escreve) são negativos.
    const negativo = /[SWO]/i.test(letra)
    return { valor: negativo ? -magnitude : magnitude, eixo: /[NS]/i.test(letra) ? 'lat' : 'lon' }
  })

  const points: number[][] = []
  for (let i = 0; i + 1 < decimais.length; i += 2) {
    const a = decimais[i]
    const b = decimais[i + 1]
    if (!a || !b) break
    // A letra diz qual é qual, então a ordem em que foram escritos não importa.
    // Um par com duas latitudes ou duas longitudes é texto malformado: descartar
    // é melhor do que inventar um ponto.
    if (a.eixo === b.eixo) return null
    const lat = a.eixo === 'lat' ? a.valor : b.valor
    const lon = a.eixo === 'lon' ? a.valor : b.valor
    if (Math.abs(lat) > 90 || Math.abs(lon) > 180) return null
    points.push([lon, lat])
  }
  if (!points.length) return null
  return { points, aviso: 'Lido em graus, minutos e segundos.' }
}

function anelDeGeoJson(bruto: string): number[][] | null {
  try {
    const dados = JSON.parse(bruto) as unknown
    const anel = procuraAnel(dados)
    return anel && anel.length >= 2 ? anel : null
  } catch {
    return null
  }
}

/** Primeira lista de pares numéricos que apareça na estrutura. */
function procuraAnel(valor: unknown): number[][] | null {
  if (Array.isArray(valor)) {
    const pares = valor.filter(
      (item): item is number[] =>
        Array.isArray(item) && item.length >= 2 && item.every((n) => typeof n === 'number'),
    )
    if (pares.length >= 2) return pares.map(([lon = 0, lat = 0]) => [lon, lat])
    for (const item of valor) {
      const achado = procuraAnel(item)
      if (achado) return achado
    }
    return null
  }
  if (valor && typeof valor === 'object') {
    for (const item of Object.values(valor)) {
      const achado = procuraAnel(item)
      if (achado) return achado
    }
  }
  return null
}
