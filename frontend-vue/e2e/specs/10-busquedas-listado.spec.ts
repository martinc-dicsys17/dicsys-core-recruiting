import type { Page } from '@playwright/test'

import { ADMIN, ClienteApi } from '../api'
import { estadoDe, expect, test } from '../fixtures'
import { sql } from '../stack'

/**
 * Listado de Búsquedas (oportunidades). Criterio legacy (oportunidades.html + GET /recruiting/oportunidades): filtros
 * contra el backend con parámetros en la URL (busqueda, estado, tipo, por_pagina, pagina), 15 o 16 columnas según el
 * permiso del líder, paginación de 20/50/100, «Asignar usuario externo» y «Cancelar búsqueda» con confirmación, y
 * acceso con el ítem «recruiting.oportunidades» (sin él: 403).
 */
const FILAS = '[data-testid="fila-busqueda"]'
const CLIENTE = 'Cliente Listado E2E'
const SUFIJO = Date.now().toString(36) // títulos únicos por corrida (el cliente no admite títulos repetidos)
const TOTAL_PROPIAS = 22 // más de una página de 20

let admin: ClienteApi
const crearBusqueda = (titulo: string, extra: Record<string, unknown> = {}) =>
  admin.post<{ id: string; titulo: string }>('/recruiting/oportunidades', { cliente: CLIENTE, titulo, estado: 'Abierta', vacantes: 1, skills: [], habilidades: [], skills_deseadas: [], ...extra })

test.beforeAll(async () => {
  admin = await ClienteApi.ingresar(ADMIN.email, ADMIN.password)
  // Idempotente: si Playwright repite el beforeAll en otro trabajador, las ya creadas (400 por título repetido) se omiten.
  const crearSiFalta = async (titulo: string, extra: Record<string, unknown> = {}) => {
    try {
      await crearBusqueda(titulo, extra)
    } catch (e) {
      if (!String(e).includes('Ya existe una búsqueda')) throw e
    }
  }
  for (let i = 1; i <= TOTAL_PROPIAS; i++) await crearSiFalta(`Listado E2E ${String(i).padStart(2, '0')}`)
  await crearSiFalta('Potencial Listado E2E', { tipo: 'Potencial' })
})

/** Espera a que el listado haya cargado (tabla visible y sin la carga en curso). */
async function esperarListado(page: Page): Promise<void> {
  await expect(page.getByTestId('indicador-registros')).toBeVisible()
  await expect(page.getByTestId('tabla-busquedas')).not.toHaveClass(/opacity-60/)
}
async function abrir(page: Page, query = ''): Promise<void> {
  await page.goto(`/recruiting/oportunidades${query}`)
  await esperarListado(page)
}
const enBase = (condicion: string): number => Number(sql(`select count(*) from recruiting_oportunidades where activo and deleted_at is null and (${condicion})`)[0]?.[0])
/** Combos nativos (como el <select> anterior): se elige por el texto visible y se lee el texto elegido. */
const elegir = (page: Page, testid: string, opcion: string) => page.getByTestId(testid).selectOption({ label: opcion })
const elegido = (page: Page, testid: string) => page.getByTestId(testid).locator('option:checked')
const totalMostrado = async (page: Page): Promise<number> => {
  const m = /de (\d+) búsquedas/.exec((await page.getByTestId('indicador-registros').innerText()).replace(/\s+/g, ' '))
  return m ? Number(m[1]) : 0
}

test.describe('acceso y carga inicial (usuario autorizado)', () => {
  test.use({ storageState: estadoDe('autorizado') })

  test('la URL original redirige a Vue; muestra las 16 columnas, el título y «+ Búsqueda»', async ({ page }) => {
    await page.goto('/recruiting/oportunidades')
    await expect(page).toHaveURL(/\/v2\/recruiting\/oportunidades/)
    await esperarListado(page)
    await expect(page.getByRole('heading', { name: 'Búsquedas', exact: true })).toBeVisible()
    await expect(page.locator('thead th')).toHaveText([
      'ID', 'Cliente', 'Búsqueda', 'Estado', 'Recruiter', 'Líder', 'Días Abierta', 'Candidatos en Pipeline', 'Coordinando entrevista',
      'Entrevistados RRHH', 'Presentación al líder', 'Feedback entrevista Líder', 'Presentación al cliente', 'Q Activos', 'Fecha de asignación', 'Acciones',
    ], { ignoreCase: true })
    await expect(page.getByTestId('nueva-busqueda')).toHaveAttribute('href', '/recruiting/oportunidades/nueva')
  })

  test('por defecto: estado Abierta, tipo Efectivas y 20 por página; el total coincide con la base', async ({ page }) => {
    await abrir(page)
    await expect(elegido(page, 'filtro-estado')).toHaveText('Abierta')
    await expect(elegido(page, 'filtro-tipo')).toHaveText('Efectivas')
    await expect(page.getByTestId('selector-limite')).toHaveValue('20')
    await expect(page.locator(FILAS)).toHaveCount(20)
    expect(await totalMostrado(page)).toBe(enBase("estado='Abierta' and tipo='Efectiva'"))
    await expect(page.getByTestId('indicador-pagina')).toHaveText(/Página 1 de [2-9]/)
  })

  test('una fila muestra cliente, título, estado y contadores; el título enlaza a la ficha', async ({ page }) => {
    await abrir(page, `?busqueda=${encodeURIComponent('Listado E2E 05')}`)
    const fila = page.locator(FILAS)
    await expect(fila).toHaveCount(1)
    await expect(fila).toContainText(CLIENTE)
    await expect(fila.getByTestId('estado-busqueda')).toHaveText('Abierta')
    const [[id]] = sql(`select id from recruiting_oportunidades where titulo='Listado E2E 05'`) as [[string]]
    await expect(fila.getByTestId('enlace-busqueda')).toHaveAttribute('href', `/recruiting/oportunidades/${id}`)
    await expect(fila.getByTestId('ver-detalle')).toHaveAttribute('href', `/recruiting/oportunidades/${id}`)
  })
})

test.describe('filtros y paginación', () => {
  test.use({ storageState: estadoDe('autorizado') })

  test('el texto se aplica con Enter y queda en la URL; «Limpiar Filtros» vuelve a los valores iniciales', async ({ page }) => {
    await abrir(page)
    await page.getByTestId('filtro-busqueda').fill('Listado E2E 07')
    await page.getByTestId('filtro-busqueda').press('Enter')
    await expect(page).toHaveURL(/busqueda=Listado\+E2E\+07|busqueda=Listado%20E2E%2007/)
    await expect(page.locator(FILAS)).toHaveCount(1)
    await page.getByTestId('limpiar-filtros').click()
    await expect(page).toHaveURL(/\/v2\/recruiting\/oportunidades$/)
    await expect(page.getByTestId('filtro-busqueda')).toHaveValue('')
    await expect(page.locator(FILAS)).toHaveCount(20)
  })

  test('el filtro de estado consulta al backend: «Todos los estados» y un estado sin búsquedas', async ({ page }) => {
    await abrir(page)
    await elegir(page, 'filtro-estado', 'Todos los estados')
    await expect(page).toHaveURL(/estado=todos/)
    await expect.poll(() => totalMostrado(page)).toBe(enBase("tipo='Efectiva'"))
    await elegir(page, 'filtro-estado', 'Suspendida')
    await expect(page).toHaveURL(/estado=Suspendida/)
    await expect(page.getByTestId('sin-resultados')).toBeVisible()
    await expect(page.getByTestId('sin-resultados')).toContainText('No se encontraron búsquedas con los filtros actuales')
    await expect(page.getByTestId('indicador-registros')).toHaveText('Sin búsquedas para mostrar')
  })

  test('el filtro de tipo: Potenciales y Todas', async ({ page }) => {
    await abrir(page)
    await elegir(page, 'filtro-tipo', 'Potenciales')
    await expect(page).toHaveURL(/tipo=Potencial/)
    await expect.poll(() => totalMostrado(page)).toBe(enBase("estado='Abierta' and tipo='Potencial'"))
    await elegir(page, 'filtro-tipo', 'Todas')
    await expect.poll(() => totalMostrado(page)).toBe(enBase("estado='Abierta'"))
  })

  test('un combo conserva el texto escrito sin aplicar (como el formulario anterior)', async ({ page }) => {
    await abrir(page)
    await page.getByTestId('filtro-busqueda').fill('Potencial Listado')
    await elegir(page, 'filtro-estado', 'Todos los estados')
    await expect(page).toHaveURL(/busqueda=Potencial/)
    await expect(page.getByTestId('filtro-busqueda')).toHaveValue('Potencial Listado')
  })

  test('paginación: siguiente, anterior y tamaño de página (50 conserva los filtros y vuelve a la primera)', async ({ page }) => {
    await abrir(page)
    const total = await totalMostrado(page)
    await expect(page.getByTestId('pagina-anterior')).toBeDisabled()
    await page.getByTestId('pagina-siguiente').click()
    await expect(page).toHaveURL(/pagina=2/)
    await expect(page.getByTestId('indicador-registros')).toContainText(`Mostrando 21 a ${Math.min(40, total)} de ${total} búsquedas`)
    await page.getByTestId('pagina-anterior').click()
    await expect(page.getByTestId('indicador-pagina')).toHaveText(/Página 1 de/)
    await elegir(page, 'selector-limite', '50')
    await expect(page).toHaveURL(/por_pagina=50/)
    await expect(page).not.toHaveURL(/[?&]pagina=/)
    await expect(page.locator(FILAS)).toHaveCount(Math.min(50, total))
  })

  test('los parámetros de la URL se respetan al entrar directo (estado, por_pagina y pagina)', async ({ page }) => {
    await abrir(page, '?estado=todos&por_pagina=20&pagina=2')
    await expect(elegido(page, 'filtro-estado')).toHaveText('Todos los estados')
    await expect(page.getByTestId('indicador-pagina')).toHaveText(/Página 2 de/)
    // estado inválido: vuelve a Abierta
    await abrir(page, '?estado=Inventado')
    await expect(elegido(page, 'filtro-estado')).toHaveText('Abierta')
  })

  test('sin resultados: mensaje y paginación vacía', async ({ page }) => {
    await abrir(page, '?busqueda=zzz-no-existe-zzz')
    await expect(page.getByTestId('sin-resultados')).toContainText('Probá restableciendo los filtros o ampliando los términos de búsqueda.')
    await expect(page.getByTestId('indicador-pagina')).toHaveText('Página 1 de 1')
  })

  test('error del servidor: aviso con «Reintentar»', async ({ page, monitor }) => {
    monitor.permitir(/^500 GET \/api\/v1\/recruiting\/oportunidades/)
    let falla = true
    await page.route(/\/api\/v1\/recruiting\/oportunidades\?/, (ruta) => (falla ? ruta.fulfill({ status: 500, json: { detail: 'Falla de prueba' } }) : ruta.continue()))
    await page.goto('/recruiting/oportunidades')
    await expect(page.getByTestId('oportunidades-error')).toContainText('Falla de prueba')
    falla = false
    await page.getByRole('button', { name: 'Reintentar' }).click()
    await expect(page.getByTestId('oportunidades-error')).toHaveCount(0)
    await expect(page.locator(FILAS).first()).toBeVisible()
  })
})

test.describe('acciones de fila (administrador)', () => {
  test.use({ storageState: estadoDe('admin') })

  test('«Cancelar búsqueda»: pide confirmación; al cancelar no cambia nada', async ({ page }) => {
    const b = await crearBusqueda(`Cancelar Rechazado E2E ${SUFIJO}`)
    await abrir(page, `?busqueda=${encodeURIComponent(b.titulo)}`)
    page.once('dialog', (d) => {
      expect(d.message()).toContain(`cancelar la búsqueda "${b.titulo}"`)
      void d.dismiss()
    })
    await page.locator(FILAS).getByTestId('cancelar-busqueda').click()
    await expect(page.locator(FILAS).getByTestId('estado-busqueda')).toHaveText('Abierta')
    expect(sql(`select estado from recruiting_oportunidades where id='${b.id}'`)[0]?.[0]).toBe('Abierta')
  })

  test('«Cancelar búsqueda»: confirma, pasa a Cancelada (la fila queda a la vista y sin el botón)', async ({ page, monitor }) => {
    const b = await crearBusqueda(`Cancelar Confirmado E2E ${SUFIJO}`)
    await abrir(page, `?busqueda=${encodeURIComponent(b.titulo)}`)
    page.once('dialog', (d) => void d.accept())
    await page.locator(FILAS).getByTestId('cancelar-busqueda').click()
    await expect(page.locator(FILAS).getByTestId('estado-busqueda')).toHaveText('Cancelada')
    await expect(page.getByText('Búsqueda cancelada correctamente.')).toBeVisible()
    await expect(page.locator(FILAS).getByTestId('cancelar-busqueda')).toHaveCount(0)
    expect(sql(`select estado from recruiting_oportunidades where id='${b.id}'`)[0]?.[0]).toBe('Cancelada')
    const puts = monitor.mutacionesDe(new RegExp(`^PUT /api/v1/recruiting/oportunidades/${b.id}$`))
    expect(puts).toHaveLength(1)
    expect(JSON.parse(puts[0]!.cuerpo ?? '{}')).toEqual({ estado: 'Cancelada' })
  })

  test('el botón de cancelar no aparece en una búsqueda Ganada ni en una ya Cancelada', async ({ page }) => {
    const ganada = await crearBusqueda(`Ganada Listado E2E ${SUFIJO}`)
    await admin.put(`/recruiting/oportunidades/${ganada.id}`, { estado: 'Ganada' })
    await abrir(page, `?estado=todos&busqueda=${encodeURIComponent(ganada.titulo)}`)
    await expect(page.locator(FILAS)).toHaveCount(1)
    await expect(page.locator(FILAS).getByTestId('cancelar-busqueda')).toHaveCount(0)
    await expect(page.locator(FILAS).getByTestId('asignar-externo')).toHaveCount(0)
  })

  test('«Asignar usuario externo»: asigna, reemplaza (con confirmación) y quita la asignación', async ({ page }) => {
    const b = await crearBusqueda(`Externo Listado E2E ${SUFIJO}`)
    await abrir(page, `?busqueda=${encodeURIComponent(b.titulo)}`)
    const fila = page.locator(FILAS)
    await fila.getByTestId('asignar-externo').click()
    const modal = page.getByTestId('modal-externo')
    await expect(modal).toContainText('Usuario externo de la búsqueda')
    await expect(modal).toContainText(b.titulo)
    await expect(page.getByTestId('externo-actual')).toHaveText('Sin asignar')
    await expect(page.getByTestId('quitar-externo')).toHaveCount(0)

    // Sin elegir nada: aviso de validación
    await page.getByTestId('guardar-externo').click()
    await expect(page.getByText('Selecciona un usuario externo.')).toBeVisible()

    await page.getByTestId('select-externo').selectOption({ index: 1 })
    await page.getByTestId('guardar-externo').click()
    await expect(page.getByText('Usuario externo asignado correctamente.')).toBeVisible()
    await expect(modal).toHaveCount(0)
    expect(sql(`select externo_id is not null from recruiting_oportunidades where id='${b.id}'`)[0]?.[0]).toBe('t')

    // Reabrir: muestra el externo asignado y permite quitarlo (con confirmación)
    await fila.getByTestId('asignar-externo').click()
    await expect(page.getByTestId('externo-actual')).toContainText('externo.e2e@dicsys.com')
    page.once('dialog', (d) => {
      expect(d.message()).toContain('Se quitara la asignacion del usuario externo')
      void d.accept()
    })
    await page.getByTestId('quitar-externo').click()
    await expect(page.getByText('Asignacion del usuario externo quitada.')).toBeVisible()
    expect(sql(`select externo_id is null from recruiting_oportunidades where id='${b.id}'`)[0]?.[0]).toBe('t')
  })

  test('el modal se cierra con «Cerrar» y con Escape', async ({ page }) => {
    const b = await crearBusqueda(`Externo Cierre E2E ${SUFIJO}`)
    await abrir(page, `?busqueda=${encodeURIComponent(b.titulo)}`)
    await page.locator(FILAS).getByTestId('asignar-externo').click()
    await page.getByTestId('cerrar-externo').click()
    await expect(page.getByTestId('modal-externo')).toHaveCount(0)
    await page.locator(FILAS).getByTestId('asignar-externo').click()
    await page.keyboard.press('Escape')
    await expect(page.getByTestId('modal-externo')).toHaveCount(0)
  })
})

test.describe('navegación', () => {
  test.use({ storageState: estadoDe('autorizado') })

  test('al abrir una búsqueda y volver, el listado conserva sus filtros; «+ Búsqueda» lleva al alta', async ({ page }) => {
    await abrir(page, `?estado=todos&por_pagina=50&busqueda=${encodeURIComponent('Listado E2E 03')}`)
    await page.locator(FILAS).getByTestId('enlace-busqueda').click()
    await expect(page).toHaveURL(/\/v2\/recruiting\/oportunidades\/[0-9a-f-]{36}/)
    await page.goBack()
    await esperarListado(page)
    await expect(page).toHaveURL(/estado=todos/)
    await expect(page).toHaveURL(/por_pagina=50/)
    await expect(page.getByTestId('filtro-busqueda')).toHaveValue('Listado E2E 03')
    await page.getByTestId('nueva-busqueda').click()
    await expect(page).toHaveURL(/\/v2\/recruiting\/oportunidades\/nueva$/)
  })

  test('el menú resalta «Búsquedas» en verde', async ({ page }) => {
    await abrir(page)
    const item = page.locator('aside a', { hasText: 'Búsquedas' }).first()
    await expect(item).toHaveClass(/emerald/)
  })
})

test.describe('usuario sin el ítem Búsquedas', () => {
  test.use({ storageState: estadoDe('sinPermiso') })

  test('las pantallas responden 403 (originales y /v2) y el backend también niega los datos', async ({ page, monitor }) => {
    monitor.permitir(/^403 GET \/(recruiting|v2|api\/v1\/recruiting)\//)
    for (const ruta of ['/recruiting/oportunidades', '/recruiting/oportunidades/nueva', '/v2/recruiting/oportunidades', '/v2/recruiting/oportunidades/nueva']) {
      const r = await page.goto(ruta)
      expect(r?.status(), ruta).toBe(403)
      await expect(page.getByTestId('indicador-registros'), ruta).toHaveCount(0)
    }
    const api = await page.request.get('/api/v1/recruiting/oportunidades?pagina=1&por_pagina=20')
    expect(api.status()).toBe(403)
  })
})
