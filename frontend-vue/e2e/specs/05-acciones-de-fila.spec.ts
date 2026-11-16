import { ClienteApi, ADMIN } from '../api'
import { estadoDe, expect, semilla, test } from '../fixtures'
import { FILAS, abrirGrilla, candidatoEnBase, filaDe } from '../helpers'
import { sql } from '../stack'

/**
 * Acciones de cada fila de la grilla. Criterio legacy (candidatos.html): CV (descarga), Asignar a búsqueda (búsquedas
 * elegibles del backend, Match > 50 %), Ver candidato, Ver Detalles (primer pipeline) y Eliminar (con confirmación; baja
 * lógica en el backend). Se comprueba el resultado real en la base y en el backend, no solo que el botón responda.
 */
test.use({ storageState: estadoDe('autorizado') })

const buscar = async (page: import('@playwright/test').Page, email: string) => {
  await abrirGrilla(page, `?busqueda=${encodeURIComponent(email)}`)
  await expect(page.locator(FILAS)).toHaveCount(1)
  return page.locator(FILAS).first()
}

test.describe('CV y detalles', () => {
  test('«CV»: solo aparece con archivo, abre en pestaña nueva y descarga el PDF real', async ({ page }) => {
    const c = semilla().candidatos.cv!
    const fila = await buscar(page, c.email)
    const enlace = fila.getByTitle('Descargar CV')
    await expect(enlace).toHaveAttribute('target', '_blank')
    const href = (await enlace.getAttribute('href'))!
    expect(href).toMatch(/^\/storage\//)
    const r = await page.request.get(href)
    expect(r.status()).toBe(200)
    expect((await r.body()).subarray(0, 4).toString()).toBe('%PDF')
    const sin = await buscar(page, semilla().candidatos.vacio!.email)
    await expect(sin.getByTitle('Descargar CV')).toHaveCount(0)
  })

  test('«Ver Detalles»: solo con pipeline; abre el detalle del primer pipeline y conserva el origen en «volver»', async ({ page }) => {
    const c = semilla().candidatos.pipeline!
    const fila = await buscar(page, c.email)
    await expect(fila.getByTestId('accion-detalles')).toHaveCount(1)
    await abrirGrilla(page, `?busqueda=${encodeURIComponent(c.email)}&limit=50`)
    const antes = page.url()
    await page.locator(FILAS).first().getByTestId('accion-detalles').click()
    await expect(page).toHaveURL(new RegExp(`/recruiting/oportunidades/${semilla().busquedas.pipeline!.id}/candidatos/${c.id}/detalle`))
    const volver = new URL(page.url()).searchParams.get('volver')!
    expect(volver).toContain('/recruiting/candidatos?')
    expect(volver).toContain('limit=50')
    expect(antes).toContain('/v2/recruiting/candidatos')
    const sin = await buscar(page, semilla().candidatos.vacio!.email)
    await expect(sin.getByTestId('accion-detalles')).toHaveCount(0)
  })
})

test.describe('asignar a búsqueda', () => {
  test('lista las búsquedas elegibles con su match, deja elegir una y asigna de verdad', async ({ page, monitor }) => {
    const c = semilla().candidatos.elegible!
    const b = semilla().busquedas.python!
    const fila = await buscar(page, c.email)
    await fila.getByTestId('accion-asignar').click()
    const dialogo = page.getByRole('dialog')
    await expect(dialogo).toContainText('Asignar a Búsqueda')
    await expect(dialogo).toContainText('Candidato: Elisa Elegible')
    const todas = dialogo.getByTestId('busqueda-elegible')
    // Elegibles: las dos búsquedas abiertas que piden Python; «Disenio Grafico E2E» (sin coincidencia de skills) no
    await expect(todas).toHaveCount(2)
    await expect(dialogo).not.toContainText('Disenio Grafico E2E')
    const opciones = todas.filter({ hasText: 'Backend Python E2E' })
    await expect(opciones).toHaveCount(1)
    await expect(opciones.first()).toContainText('Cliente E2E')
    await expect(opciones.first()).toContainText(/\d+% match/)
    await expect(opciones.first()).toContainText('Python')
    const match = Number(/(\d+)% match/.exec(await opciones.first().innerText())![1])
    expect(match).toBeGreaterThan(50) // umbral de elegibilidad del backend
    // «Confirmar Asignación» deshabilitado hasta elegir
    const confirmar = dialogo.getByTestId('confirmar-asignacion')
    await expect(confirmar).toBeDisabled()
    await opciones.first().click()
    await expect(confirmar).toBeEnabled()
    await confirmar.click()
    await expect(page.getByText('Candidato asignado a la búsqueda correctamente')).toBeVisible()
    await expect(dialogo).toHaveCount(0)

    // Persistencia real: el backend ya lo tiene postulado y deja de ofrecer esa búsqueda
    const admin = await ClienteApi.ingresar(ADMIN.email, ADMIN.password)
    const post = await admin.get<{ oportunidad_id?: string; id?: string }[]>(`/recruiting/candidatos/${c.id}/postulaciones`)
    expect(JSON.stringify(post)).toContain(b.id)
    const elegibles = await admin.get<{ id: string }[]>(`/recruiting/candidatos/${c.id}/busquedas-elegibles`)
    expect(elegibles.map((e) => e.id)).not.toContain(b.id)
    expect(monitor.mutacionesDe(new RegExp(`POST /recruiting/oportunidades/${b.id}/candidatos`))).toHaveLength(1)
    expect(monitor.mutacionesDe(new RegExp(`POST /recruiting/oportunidades/${b.id}/candidatos`))[0]!.cuerpo).toContain(c.id)

    // Al reabrir, la búsqueda ya asignada no se ofrece (queda solo la otra elegible)
    await page.reload()
    await page.locator(FILAS).first().getByTestId('accion-asignar').click()
    await expect(page.getByRole('dialog').getByTestId('busqueda-elegible')).toHaveCount(1)
    await expect(page.getByRole('dialog')).not.toContainText('Backend Python E2E')
  })

  test('candidato sin coincidencias: mensaje «No hay ninguna búsqueda que pueda aplicar» y sin botón de confirmar', async ({ page }) => {
    const fila = await buscar(page, semilla().candidatos.vacio!.email)
    await fila.getByTestId('accion-asignar').click()
    const dialogo = page.getByRole('dialog')
    await expect(dialogo.getByTestId('sin-busquedas')).toContainText('No hay ninguna búsqueda que pueda aplicar.')
    await expect(dialogo.getByTestId('confirmar-asignacion')).toHaveCount(0)
    await dialogo.getByRole('button', { name: 'Cancelar' }).click()
    await expect(dialogo).toHaveCount(0)
  })

  test('Cancelar y cerrar no asignan nada', async ({ page, monitor }) => {
    const c = semilla().candidatos.cv!
    const fila = await buscar(page, c.email)
    await fila.getByTestId('accion-asignar').click()
    await expect(page.getByRole('dialog')).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(page.getByRole('dialog')).toHaveCount(0)
    expect(monitor.mutacionesDe(/POST .*\/candidatos$/)).toHaveLength(0)
  })
})

test.describe('eliminar candidato', () => {
  test('Cancelar conserva al candidato (sigue en la grilla y en la base)', async ({ page, monitor }) => {
    const c = semilla().candidatos.eliminar1!
    const fila = await buscar(page, c.email)
    await fila.getByTestId('accion-eliminar').click()
    const dialogo = page.getByRole('dialog')
    await expect(dialogo.getByTestId('texto-eliminar')).toContainText('¿Estás seguro de que deseas eliminar permanentemente a "Elias Eliminable" de la base de datos? Esta acción no se puede deshacer.')
    await dialogo.getByRole('button', { name: 'Cancelar' }).click()
    await expect(dialogo).toHaveCount(0)
    expect(monitor.mutacionesDe(/DELETE/)).toHaveLength(0)
    await expect(page.locator(FILAS)).toHaveCount(1)
    expect(candidatoEnBase(c.email, 'activo, deleted_at is null')).toEqual(['t', 't'])
  })

  test('confirmar elimina: desaparece de la grilla y el backend lo da de baja (baja lógica)', async ({ page, monitor }) => {
    const c = semilla().candidatos.eliminar1!
    const fila = await buscar(page, c.email)
    await fila.getByTestId('accion-eliminar').click()
    await page.getByTestId('confirmar-eliminar').click()
    await expect(page.getByText('Candidato eliminado correctamente')).toBeVisible()
    await expect(page.getByRole('dialog')).toHaveCount(0)
    await expect(page.getByTestId('sin-candidatos')).toBeVisible() // la búsqueda ya no lo encuentra
    expect(monitor.mutacionesDe(new RegExp(`DELETE /api/v1/recruiting/candidatos/${c.id}`))).toHaveLength(1)
    // El backend original NO borra la fila: la marca como baja (activo=false, deleted_at)
    expect(candidatoEnBase(c.email, 'activo, deleted_at is not null')).toEqual(['f', 't'])
    // y no vuelve a aparecer tras recargar, ni en la búsqueda general
    await page.reload()
    await expect(page.getByTestId('sin-candidatos')).toBeVisible()
    await abrirGrilla(page, '?busqueda=Eliminable')
    await expect(filaDe(page, 'Elias')).toHaveCount(0)
    await expect(filaDe(page, 'Emma')).toHaveCount(1) // el otro candidato de prueba sigue
  })

  test('la ficha de un candidato eliminado ya no se puede abrir', async ({ page, monitor }) => {
    monitor.permitir(/^40[34] GET \/api\/v1\/recruiting\/candidatos\//)
    await page.goto(`/recruiting/candidatos/${semilla().candidatos.eliminar1!.id}`)
    await expect(page.getByTestId('detalle-error')).toBeVisible()
  })

  test('el total de la grilla baja en uno respecto de la base', async ({ page }) => {
    await abrirGrilla(page)
    const [fila] = sql('select count(*) from recruiting_candidatos where activo and deleted_at is null')
    await expect(page.getByTestId('indicador-registros')).toContainText(`de ${fila![0]} candidatos`)
  })
})
