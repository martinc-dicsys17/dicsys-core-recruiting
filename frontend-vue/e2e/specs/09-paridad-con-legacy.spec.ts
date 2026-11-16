import { estadoDe, expect, semilla, test } from '../fixtures'
import { abrirGrilla, esperarGrilla } from '../helpers'

/**
 * Correcciones de paridad con la pantalla anterior: chips que solo vacían el campo al agregar, Disponibilidad y
 * Observaciones sin viajar en el alta, cierre de modales con clic afuera, «Sin candidatos» oculto mientras carga,
 * encabezado de la ficha alineado con el de la grilla y vuelta al login ante una sesión vencida (401).
 */
test.use({ storageState: estadoDe('autorizado') })

test.describe('Nuevo Candidato', () => {
  test('chips: con un valor vacío o repetido el campo queda como está; al agregar se vacía', async ({ page }) => {
    await page.goto('/recruiting/candidatos/nuevo')
    await expect(page.getByTestId('guardar')).toBeVisible()
    const campo = page.locator('#skills')
    await campo.fill('   ')
    await campo.press('Enter')
    await expect(campo).toHaveValue('   ')
    await campo.fill('Docker')
    await campo.press('Enter')
    await expect(campo).toHaveValue('')
    await expect(page.getByTestId('skills-elegidas')).toContainText('Docker')
    await campo.fill('Docker')
    await campo.press('Enter')
    await expect(campo).toHaveValue('Docker') // repetido: no se agrega ni se vacía
    await expect(page.getByTestId('skills-elegidas').getByText('Docker')).toHaveCount(1)
  })

  test('Disponibilidad (Inmediata) y Observaciones se muestran y no viajan en el alta', async ({ page, monitor }) => {
    await page.goto('/recruiting/candidatos/nuevo')
    await expect(page.locator('#disponibilidad')).toHaveText('Inmediata')
    await page.locator('#disponibilidad').click()
    expect(await page.getByRole('option').allInnerTexts()).toEqual(['Inmediata', '2 semanas (preaviso estándar)', '1 mes', 'A convenir'])
    await page.getByRole('option', { name: '1 mes', exact: true }).click()
    await page.locator('#observaciones').fill('nota interna')
    await page.locator('#nombre').fill('Paridad')
    await page.locator('#apellido').fill('Legacy')
    await page.locator('#email').fill('paridad.legacy.e2e@example.com')
    await page.locator('#telefono').fill('3515550000')
    await page.getByTestId('guardar').click()
    await expect.poll(() => monitor.mutacionesDe(/POST \/api\/v1\/recruiting\/candidatos$/).length).toBe(1)
    const cuerpo = monitor.mutacionesDe(/POST \/api\/v1\/recruiting\/candidatos$/)[0]!.cuerpo ?? ''
    expect(cuerpo).not.toContain('disponibilidad')
    expect(cuerpo).not.toContain('observaciones')
    expect(cuerpo).toContain('Semi Senior')
  })
})

test.describe('Grilla', () => {
  test('mientras carga no se muestra «Sin candidatos»', async ({ page }) => {
    let soltar = () => {}
    const demora = new Promise<void>((ok) => (soltar = ok))
    await page.route('**/api/v1/recruiting/candidatos?*', async (ruta) => {
      await demora
      await ruta.continue()
    })
    await page.goto('/recruiting/candidatos')
    await expect(page.locator('.p-datatable-mask')).toBeVisible()
    await expect(page.getByTestId('sin-candidatos')).toHaveCount(0)
    await expect(page.getByText('Sin candidatos para mostrar')).toHaveCount(0)
    soltar()
    await esperarGrilla(page)
  })

  test('los modales de carga individual y de asignar se cierran con un clic afuera', async ({ page }) => {
    await abrirGrilla(page)
    await page.getByTestId('abrir-carga-individual').click()
    await expect(page.getByRole('dialog')).toBeVisible()
    await page.mouse.click(5, 5)
    await expect(page.getByRole('dialog')).toHaveCount(0)
    await page.getByTestId('abrir-carga-masiva').click()
    await expect(page.getByTestId('modal-carga-masiva')).toBeVisible()
    await page.mouse.click(5, 5)
    await expect(page.getByTestId('modal-carga-masiva')).toHaveCount(0)
  })
})

test.describe('Ficha', () => {
  test('el encabezado queda alineado con el de la grilla', async ({ page }) => {
    await abrirGrilla(page)
    const grilla = await page.locator('main h1').first().boundingBox()
    await page.goto(`/recruiting/candidatos/${semilla().candidatos.cv!.id}`)
    await expect(page.locator('main h1').first()).toBeVisible()
    const ficha = await page.locator('main h1').first().boundingBox()
    expect(Math.round(ficha!.x)).toBe(Math.round(grilla!.x))
  })

  test('sesión vencida (401): vuelve al login', async ({ page, monitor }) => {
    monitor.permitir(/401/, /Failed to load resource/)
    await page.route('**/api/v1/recruiting/candidatos/*', (ruta) =>
      ruta.fulfill({ status: 401, contentType: 'application/json', body: JSON.stringify({ detail: 'Tu sesión venció: volvé a iniciar sesión' }) }),
    )
    await page.goto(`/recruiting/candidatos/${semilla().candidatos.cv!.id}`)
    await expect(page).toHaveURL(/\/login/)
  })
})
