import type { Page } from '@playwright/test'

import { estadoDe, expect, semilla, test } from '../fixtures'
import { FILAS, abrirGrilla, contarEnBase, elegir, esperarGrilla, totalMostrado } from '../helpers'

/**
 * Diagnóstico de la sincronización del buscador de la grilla (texto visible, estado interno = URL, parámetros enviados al
 * backend y resultados devueltos) al ir a la ficha y volver. Cada prueba adjunta la línea de tiempo (consultas, parámetros,
 * totales y estado del buscador). Criterio legacy: el buscador, la URL, la consulta y la tabla siempre coinciden; «Limpiar
 * Filtros» recarga la página y deja el buscador vacío; cualquier cambio de filtro aplica también el texto escrito.
 */
test.use({ storageState: estadoDe('autorizado') })

interface Evento {
  t: number
  evento: string
  detalle: Record<string, unknown>
}

function lineaDeTiempo(page: Page) {
  const inicio = Date.now()
  const eventos: Evento[] = []
  const anotar = (evento: string, detalle: Record<string, unknown>) => eventos.push({ t: Date.now() - inicio, evento, detalle })
  page.on('request', (r) => {
    if (/\/api\/v1\/recruiting\/candidatos\?/.test(r.url())) anotar('consulta', Object.fromEntries(new URL(r.url()).searchParams))
  })
  page.on('response', async (r) => {
    if (/\/api\/v1\/recruiting\/candidatos\?/.test(r.url())) {
      const p = Object.fromEntries(new URL(r.url()).searchParams)
      const cuerpo = (await r.json().catch(() => null)) as { total?: number; items?: unknown[] } | null
      anotar('respuesta', { busqueda: p.busqueda ?? null, estado: r.status(), total: cuerpo?.total ?? null, filas: cuerpo?.items?.length ?? null })
    }
  })
  page.on('framenavigated', (f) => {
    if (f === page.mainFrame()) anotar('navegacion', { url: f.url().replace(/^https?:\/\/[^/]+/, '') })
  })
  return {
    eventos,
    anotar,
    /** Estado visible, URL y consulta más reciente al backend: deben coincidir. */
    async estado(etiqueta: string) {
      const entrada = await page.getByTestId('filtro-busqueda').inputValue().catch(() => null)
      const url = new URL(page.url())
      const ultima = [...eventos].reverse().find((e) => e.evento === 'consulta')
      const respuesta = [...eventos].reverse().find((e) => e.evento === 'respuesta')
      const total = await totalMostrado(page).catch(() => null)
      const e = { entrada, urlBusqueda: url.searchParams.get('busqueda') ?? '', consultaBusqueda: (ultima?.detalle.busqueda as string | undefined) ?? '', respuestaTotal: respuesta?.detalle.total ?? null, totalVisible: total }
      anotar(`estado: ${etiqueta}`, e)
      return e
    },
    async adjuntar(info: typeof test.info extends () => infer R ? R : never) {
      await info.attach('linea-de-tiempo.json', { body: JSON.stringify(eventos, null, 2), contentType: 'application/json' })
    },
  }
}

const coherente = (e: { entrada: string | null; urlBusqueda: string; consultaBusqueda: string }) => {
  expect(e.entrada, 'texto visible = URL').toBe(e.urlBusqueda)
  expect(e.consultaBusqueda, 'consulta al backend = URL').toBe(e.urlBusqueda)
}

test.describe('Volver y Atrás con una búsqueda previa (Ana)', () => {
  test('1) Volver normal: listado sin filtros y todo coherente', async ({ page }, info) => {
    const lt = lineaDeTiempo(page)
    await abrirGrilla(page, '?busqueda=Ana')
    await lt.estado('grilla con «Ana»')
    const filtrada = await totalMostrado(page)
    expect(filtrada).toBeGreaterThan(0)
    expect(filtrada).toBeLessThan(contarEnBase())
    await page.getByTestId('accion-ver').first().click()
    await expect(page.getByTestId('detalle-nombre')).toBeVisible()
    await page.getByTestId('volver').click()
    await esperarGrilla(page)
    await expect.poll(async () => (await lt.estado('tras Volver')).respuestaTotal).toBe(contarEnBase())
    const e = await lt.estado('tras Volver (estable)')
    coherente(e)
    expect(e).toMatchObject({ entrada: '', urlBusqueda: '', totalVisible: contarEnBase() })
    await lt.adjuntar(info)
  })

  test('2) Atrás del navegador: URL, texto y resultados de «Ana» restaurados', async ({ page }, info) => {
    const lt = lineaDeTiempo(page)
    await abrirGrilla(page, '?busqueda=Ana')
    const filtrada = await totalMostrado(page)
    await page.getByTestId('accion-ver').first().click()
    await expect(page.getByTestId('detalle-nombre')).toBeVisible()
    await page.goBack()
    await esperarGrilla(page)
    await expect.poll(async () => (await lt.estado('tras Atrás')).totalVisible).toBe(filtrada)
    const e = await lt.estado('tras Atrás (estable)')
    coherente(e)
    expect(e.entrada).toBe('Ana')
    await lt.adjuntar(info)
  })

  test('3) Volver con ?volver=…busqueda=Ana: se restaura la búsqueda en todos los niveles', async ({ page }, info) => {
    const lt = lineaDeTiempo(page)
    const id = semilla().candidatos.completo!.id
    await page.goto(`/recruiting/candidatos/${id}?volver=${encodeURIComponent('/recruiting/candidatos?page=1&limit=20&busqueda=Ana')}`)
    await expect(page.getByTestId('detalle-nombre')).toBeVisible()
    await page.getByTestId('volver').click()
    await esperarGrilla(page)
    const filtrada = (await lt.estado('tras Volver')).respuestaTotal
    expect(filtrada).toBeGreaterThan(0)
    await expect.poll(async () => (await lt.estado('estable')).totalVisible).toBe(filtrada)
    const e = await lt.estado('tras Volver con volver (estable)')
    coherente(e)
    expect(e.entrada).toBe('Ana')
    await lt.adjuntar(info)
  })

  test('4) Volver con la API lenta: nunca se ve un resultado filtrado con el buscador vacío (ni al revés)', async ({ page }, info) => {
    const lt = lineaDeTiempo(page)
    await page.route(/\/api\/v1\/recruiting\/candidatos\?/, async (r) => {
      await new Promise((ok) => setTimeout(ok, 1500))
      await r.continue()
    })
    await abrirGrilla(page, '?busqueda=Ana')
    await page.getByTestId('accion-ver').first().click()
    await expect(page.getByTestId('detalle-nombre')).toBeVisible()
    await page.getByTestId('volver').click()
    // Se muestrea el estado durante toda la carga: texto visible = URL y, cuando hay datos, el total visible = el de la consulta vigente
    const muestras: Array<{ entrada: string | null; url: string; total: number | null; cargando: boolean }> = []
    for (let i = 0; i < 12; i++) {
      await page.waitForTimeout(400)
      muestras.push({
        entrada: await page.getByTestId('filtro-busqueda').inputValue().catch(() => null),
        url: new URL(page.url()).searchParams.get('busqueda') ?? '',
        total: await totalMostrado(page).catch(() => null),
        cargando: (await page.locator('.p-datatable-mask').count().catch(() => 0)) > 0,
      })
    }
    lt.anotar('muestras', { muestras })
    const asentado = muestras.at(-1)!
    for (const m of muestras.filter((x) => x.entrada !== null)) expect(m.entrada, 'texto visible = URL durante la carga').toBe(m.url)
    expect(asentado).toMatchObject({ entrada: '', url: '', total: contarEnBase(), cargando: false })
    await lt.adjuntar(info)
  })
})

test.describe('texto escrito sin Enter (el buscador aplica con Enter, pero el legacy lo aplicaba con cualquier cambio de filtro)', () => {
  test('5) escribir «Ana» sin Enter y cambiar un combo: el texto se aplica (legacy: irAPagina leía this.busqueda)', async ({ page }, info) => {
    const lt = lineaDeTiempo(page)
    await abrirGrilla(page)
    await page.getByTestId('filtro-busqueda').fill('Ana')
    await elegir(page, 'filtro-seniority', 'Senior')
    await esperarGrilla(page)
    await page.waitForTimeout(800)
    const e = await lt.estado('tras cambiar el combo con «Ana» escrito')
    await lt.adjuntar(info)
    // Coherencia: lo que se ve en el buscador debe ser lo que se consultó y lo que está en la URL
    coherente(e)
  })

  test('6) escribir «Ana» sin Enter y «Limpiar Filtros»: el buscador queda vacío (legacy recargaba la página)', async ({ page }, info) => {
    const lt = lineaDeTiempo(page)
    await abrirGrilla(page)
    await page.getByTestId('filtro-busqueda').fill('Ana')
    await page.getByTestId('limpiar-filtros').click()
    await esperarGrilla(page)
    await page.waitForTimeout(800)
    const e = await lt.estado('tras Limpiar con «Ana» escrito')
    await lt.adjuntar(info)
    expect(e.entrada).toBe('')
    coherente(e)
    expect(FILAS).toBeTruthy()
  })
})
