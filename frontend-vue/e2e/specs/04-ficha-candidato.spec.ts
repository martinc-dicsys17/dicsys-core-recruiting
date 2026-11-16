import { estadoDe, expect, semilla, test } from '../fixtures'
import { esperarGrilla, filaDe } from '../helpers'

/**
 * Ver candidato (ficha). Criterio legacy (candidato_detalle.html): modo lectura con todos los campos en solo lectura,
 * valores por defecto cuando faltan datos (Seniority «Semi Senior», Modalidad «Remoto», Fuente «Portal Propio»,
 * Disponibilidad «Inmediata»), pretensión «$ 1.500.000 ARS» / «US$ … USD» / «-», botones Agregar a Blacklist (solo
 * confirma y avisa que aún no está disponible), Editar (la edición sigue en la pantalla de Flask) y Volver (?volver=).
 */
test.use({ storageState: estadoDe('autorizado') })

const ir = async (page: import('@playwright/test').Page, id: string, query = '') => {
  await page.goto(`/recruiting/candidatos/${id}${query}`)
  await expect(page.getByTestId('detalle-nombre')).toBeVisible()
}
const valor = (page: import('@playwright/test').Page, etiqueta: string) => page.locator('label', { hasText: etiqueta }).first().locator('xpath=following-sibling::*[1]')

test.describe('acceso desde la grilla', () => {
  test('el nombre y el ojo de cada fila llevan a la ficha (/recruiting/candidatos/<id>)', async ({ page }) => {
    const c = semilla().candidatos.completo!
    await page.goto(`/recruiting/candidatos?busqueda=${c.email}`)
    await esperarGrilla(page)
    const fila = filaDe(page, c.apellido)
    await expect(fila.getByTestId('accion-ver')).toHaveAttribute('href', `/recruiting/candidatos/${c.id}`)
    await expect(fila.getByRole('link', { name: 'Camila Completa' })).toHaveAttribute('href', `/recruiting/candidatos/${c.id}`)
    await fila.getByTestId('accion-ver').click()
    await expect(page).toHaveURL(new RegExp(`/v2/recruiting/candidatos/${c.id}$`))
    await expect(page.getByTestId('detalle-nombre')).toHaveText('Camila Completa')
  })
})

test.describe('datos mostrados', () => {
  test('candidato completo: todas las secciones y valores', async ({ page }) => {
    const c = semilla().candidatos.completo!
    await ir(page, c.id)
    await expect(page.getByTestId('detalle-nombre')).toHaveText('Camila Completa')
    await expect(page.locator('h1 + span')).toHaveText('Activo')
    await expect(page.locator('h1').locator('xpath=ancestor::div[2]//p')).toHaveText('Desarrollador Backend')
    // Datos personales y de contacto
    await expect(page.getByRole('heading', { name: 'Datos Personales y Contacto' })).toBeVisible()
    await expect(page.locator('input[placeholder="Nombres"]')).toHaveValue('Camila')
    await expect(page.locator('input[placeholder="Apellido"]')).toHaveValue('Completa')
    await expect(page.locator('input[placeholder="ejemplo@correo.com"]')).toHaveValue('camila.completa@example.com')
    await expect(page.locator('input[placeholder="ej: +54 9 351 1234567"]')).toHaveValue('+5493515550101')
    await expect(page.getByTestId('detalle-provincia')).toContainText('Cordoba')
    await expect(page.getByTestId('detalle-ciudad')).toContainText('Cordoba Capital')
    await expect(page.locator('input[placeholder="https://linkedin.com/in/usuario"]')).toHaveValue('https://linkedin.com/in/camila-completa')
    await expect(page.getByTitle('Abrir perfil de LinkedIn')).toHaveAttribute('href', 'https://linkedin.com/in/camila-completa')
    await expect(page.locator('input[placeholder="—"]')).toHaveValue('30111222')
    await expect(page.locator('input[placeholder="DD-MM-YYYY"]')).toHaveValue('17-05-1990')
    // Perfil profesional
    await expect(page.getByRole('heading', { name: 'Perfil Profesional' })).toBeVisible()
    await expect(page.getByTestId('detalle-puesto')).toContainText('Desarrollador Backend')
    await expect(page.getByTestId('detalle-seniority')).toHaveValue('Semi Senior')
    await expect(page.getByTestId('detalle-modalidad')).toHaveValue('Híbrido')
    await expect(page.getByTestId('detalle-salario')).toHaveText('$ 1.500.000 ARS')
    await expect(page.locator('input[placeholder="Portal Propio"]')).toHaveValue('LinkedIn')
    await expect(page.getByTestId('detalle-skills').locator('span.inline-flex')).toHaveCount(5)
    await expect(page.getByTestId('detalle-habilidades')).toContainText('Liderazgo')
    await expect(page.getByTestId('detalle-habilidades')).toContainText('Trabajo en equipo')
    await expect(page.getByTestId('detalle-disponibilidad')).toHaveValue('Inmediata')
    await expect(page.locator('textarea')).toHaveValue('')
    // Todos los campos son de solo lectura
    for (const e of await page.locator('form input, form select, form textarea').all()) await expect(e).toBeDisabled()
    // Sin errores de carga ni aviso de ubicación registrada distinta
    await expect(page.getByText('Ubicación registrada:')).toHaveCount(0)
    await expect(page.getByTestId('perfiles-puesto-error')).toHaveCount(0)
  })

  test('pretensión en dólares', async ({ page }) => {
    await ir(page, semilla().candidatos.usd!.id)
    await expect(page.getByTestId('detalle-salario')).toHaveText('US$ 4.200 USD')
    await expect(page.getByTestId('detalle-provincia')).toContainText('Buenos Aires')
    await expect(page.getByTestId('detalle-modalidad')).toHaveValue('Remoto')
  })

  test('candidato casi vacío: valores por defecto y textos de «sin datos»', async ({ page }) => {
    await ir(page, semilla().candidatos.vacio!.id)
    await expect(page.getByTestId('detalle-nombre')).toHaveText('Vera Vacia')
    await expect(page.locator('h1').locator('xpath=ancestor::div[2]//p')).toHaveText('Ficha del Candidato')
    await expect(page.getByTestId('detalle-seniority')).toHaveValue('Semi Senior')
    await expect(page.getByTestId('detalle-modalidad')).toHaveValue('Remoto')
    await expect(page.locator('input[placeholder="Portal Propio"]')).toHaveValue('Portal Propio')
    await expect(page.getByTestId('detalle-salario')).toHaveText('-')
    await expect(page.getByTestId('detalle-skills')).toHaveText('Sin tecnologías registradas.')
    await expect(page.getByTestId('detalle-habilidades')).toHaveText('Sin habilidades o competencias registradas.')
    await expect(page.getByTestId('detalle-provincia')).toContainText('Seleccionar provincia...')
    await expect(page.getByTestId('detalle-ciudad')).toContainText('Seleccionar ciudad...')
    await expect(page.getByTestId('detalle-puesto')).toContainText('Seleccionar puesto...')
    await expect(page.locator('input[placeholder="DD-MM-YYYY"]')).toHaveValue('')
    await expect(page.getByText('Sin archivo cargado')).toBeVisible()
    await expect(page.getByText('No disponible')).toBeVisible()
    await expect(page.getByTestId('descargar-cv')).toHaveCount(0)
    await expect(page.getByText('Vera_Vacia_CV')).toBeVisible()
  })

  test('estados del encabezado: color según el estado', async ({ page }) => {
    await ir(page, semilla().candidatos.rechazado!.id)
    await expect(page.locator('h1 + span')).toHaveText('Rechazado')
    await expect(page.locator('h1 + span')).toHaveClass(/bg-red-100/)
    await ir(page, semilla().candidatos.sinrespuesta!.id)
    await expect(page.locator('h1 + span')).toHaveText('Sin respuesta')
    await expect(page.locator('h1 + span')).toHaveClass(/bg-amber-100/)
  })

  test('CV adjunto: nombre del archivo y descarga real del documento', async ({ page }) => {
    await ir(page, semilla().candidatos.cv!.id)
    await expect(page.getByText('Documento digital adjunto')).toBeVisible()
    const enlace = page.getByTestId('descargar-cv')
    await expect(enlace).toHaveAttribute('target', '_blank')
    const href = (await enlace.getAttribute('href'))!
    expect(href.startsWith('/storage/')).toBe(true)
    const r = await page.request.get(href)
    expect(r.status()).toBe(200)
    expect(r.headers()['content-type']).toContain('pdf')
    expect((await r.body()).subarray(0, 4).toString()).toBe('%PDF')
  })
})

test.describe('acciones del encabezado', () => {
  test('Agregar a Blacklist: confirma con el nombre, Cancelar cierra y «Sí, agregar» solo avisa que no está disponible', async ({ page, monitor }) => {
    await ir(page, semilla().candidatos.completo!.id)
    await page.locator('#btn-agregar-blacklist').click()
    const modal = page.getByRole('dialog', { name: '¿Agregar a Blacklist?' })
    await expect(modal).toContainText('¿Estás seguro de mandar a Camila Completa a la Blacklist?')
    await modal.getByRole('button', { name: 'Cancelar' }).click()
    await expect(modal).toHaveCount(0)
    await page.locator('#btn-agregar-blacklist').click()
    await page.mouse.click(5, 5) // clic fuera de la tarjeta: cierra (legacy: @click.self)
    await expect(modal).toHaveCount(0)
    await page.locator('#btn-agregar-blacklist').click()
    await page.getByRole('button', { name: 'Sí, agregar' }).click()
    await expect(page.getByRole('status')).toHaveText('El alta a Blacklist todavía no está disponible.')
    await expect(page.getByRole('status')).toHaveCount(0, { timeout: 8000 }) // el aviso se oculta solo
    expect(monitor.mutaciones, 'no llama a ningún endpoint').toHaveLength(0)
  })

  // Legacy: <div @keydown.escape.window="confirmarBlacklist = false"> (Alpine). En Vue `.window` no existe como modificador.
  test('Agregar a Blacklist: la tecla Escape cierra el modal', async ({ page }) => {
    await ir(page, semilla().candidatos.completo!.id)
    await page.locator('#btn-agregar-blacklist').click()
    const modal = page.getByRole('dialog', { name: '¿Agregar a Blacklist?' })
    await expect(modal).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(modal).toHaveCount(0, { timeout: 3000 })
  })

  test('Editar abre la pantalla de edición existente (Flask) en modo edición', async ({ page }) => {
    const c = semilla().candidatos.completo!
    await ir(page, c.id, '?volver=/recruiting/candidatos?page=2')
    await page.getByTestId('editar').click()
    await expect(page).toHaveURL(new RegExp(`/recruiting/candidatos/${c.id}\\?editar=1`))
    await expect(page).not.toHaveURL(/\/v2\//)
    await expect(page.getByRole('heading', { name: 'Editar Ficha del Candidato' })).toBeVisible()
    await expect(page.getByText('Modo Edición')).toBeVisible()
    await expect(page.locator('input[name="nombre"]')).toHaveValue('Camila')
    await expect(page.locator('input[name="nombre"]')).toBeEnabled()
    await expect(page.getByRole('button', { name: 'Guardar Cambios' }).first()).toBeVisible()
  })

  test('Volver: respeta ?volver= de Recruiting, ignora destinos externos y por defecto va al listado', async ({ page }) => {
    const id = semilla().candidatos.completo!.id
    await ir(page, id, '?volver=/recruiting/candidatos?page=2%26limit=50')
    await expect(page.getByTestId('volver')).toHaveAttribute('href', '/recruiting/candidatos?page=2&limit=50')
    await page.getByTestId('volver').click()
    await expect(page).toHaveURL(/\/v2\/recruiting\/candidatos\?page=2&limit=50/)

    await ir(page, id, '?volver=https://sitio-externo.example/x')
    await expect(page.getByTestId('volver')).toHaveAttribute('href', '/recruiting/candidatos')
    await ir(page, id, '?volver=/otra/ruta')
    await expect(page.getByTestId('volver')).toHaveAttribute('href', '/recruiting/candidatos')
    await ir(page, id)
    await page.getByTestId('volver').click()
    await expect(page).toHaveURL(/\/v2\/recruiting\/candidatos$/)
  })
})

test.describe('casos de error', () => {
  test('un candidato inexistente muestra el mensaje del backend con «Volver» (el legacy redirigía al listado con ese aviso)', async ({ page, monitor }) => {
    monitor.permitir(/^404 GET \/api\/v1\/recruiting\/candidatos\//)
    await page.goto('/recruiting/candidatos/00000000-0000-4000-8000-000000000000')
    await expect(page.getByTestId('detalle-error')).toBeVisible()
    await expect(page.getByTestId('detalle-error').getByRole('link', { name: 'Volver' })).toHaveAttribute('href', '/recruiting/candidatos')
  })

  test('un id que no es UUID responde 404 sin llegar al backend', async ({ page, monitor }) => {
    monitor.permitir(/^404 GET \/recruiting\/candidatos\/no-es-un-uuid/)
    const r = await page.goto('/recruiting/candidatos/no-es-un-uuid')
    expect(r?.status()).toBe(404)
  })
})
