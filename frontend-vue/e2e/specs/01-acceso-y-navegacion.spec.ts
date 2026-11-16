import { estadoDe, expect, semilla, test } from '../fixtures'

/**
 * Permisos y navegación. Criterio legacy: las URLs /recruiting/candidatos[/nuevo|/<id>] exigen sesión y el ítem
 * «recruiting.candidatos» (sin sesión: login; sin el ítem: 403), y llevan a la pantalla Vue.
 */
test.describe('usuario autorizado', () => {
  test.use({ storageState: estadoDe('autorizado') })

  test('las tres URLs originales redirigen a la pantalla Vue', async ({ page }) => {
    const id = semilla().candidatos.completo!.id
    await page.goto('/recruiting/candidatos')
    await expect(page).toHaveURL(/\/v2\/recruiting\/candidatos$/)
    await expect(page.getByTestId('indicador-registros')).toBeVisible()

    await page.goto('/recruiting/candidatos/nuevo')
    await expect(page).toHaveURL(/\/v2\/recruiting\/candidatos\/nuevo$/)
    await expect(page.getByTestId('guardar')).toBeVisible()

    await page.goto(`/recruiting/candidatos/${id}`)
    await expect(page).toHaveURL(new RegExp(`/v2/recruiting/candidatos/${id}$`))
    await expect(page.getByTestId('detalle-nombre')).toHaveText('Camila Completa')
  })

  test('acceso directo a las URLs /v2 (con permiso: abren)', async ({ page }) => {
    const id = semilla().candidatos.completo!.id
    for (const [ruta, marca] of [
      ['/v2/recruiting/candidatos', 'indicador-registros'],
      ['/v2/recruiting/candidatos/nuevo', 'guardar'],
      [`/v2/recruiting/candidatos/${id}`, 'detalle-nombre'],
    ] as const) {
      const r = await page.goto(ruta)
      expect(r?.status(), ruta).toBe(200)
      await expect(page.getByTestId(marca), ruta).toBeVisible()
    }
  })

  test('el menú lleva a la grilla y resalta «Candidatos» en verde (grilla y ficha)', async ({ page }) => {
    await page.goto('/')
    await page.locator('aside').getByText('Recruiting', { exact: true }).first().click()
    await page.locator('aside a', { hasText: 'Candidatos' }).first().click()
    await expect(page).toHaveURL(/\/v2\/recruiting\/candidatos/)
    const item = page.locator('aside a', { hasText: 'Candidatos' }).first()
    await expect(item).toHaveAttribute('aria-current', 'page')
    await expect(item).toHaveClass(/emerald/)

    // Navegación interna de Vue: de la grilla a la ficha, el ítem sigue activo.
    await page.getByTestId('accion-ver').first().click()
    await expect(page).toHaveURL(/\/recruiting\/candidatos\/[0-9a-f-]{36}/)
    await expect(page.getByTestId('detalle-nombre')).toBeVisible()
    await expect(page.locator('aside a', { hasText: 'Candidatos' }).first()).toHaveAttribute('aria-current', 'page')
    // Blacklist: verde y sin etiqueta VUE
    await expect(page.locator('aside a', { hasText: 'Blacklist' }).first()).toHaveClass(/emerald/)
    await expect(page.locator('aside').getByText('VUE', { exact: true })).toHaveCount(0)
  })

  test('el backend responde con los permisos del usuario (reclutador: todas las acciones)', async ({ page }) => {
    const r = await page.request.get('/api/v1/recruiting/candidatos/permisos')
    expect(r.status()).toBe(200)
    expect(await r.json()).toEqual({ puede_eliminar_candidatos: true, puede_cargar_cv_general: true, puede_carga_masiva: true, puede_asignar_candidatos: true })
  })
})

test.describe('usuario sin el ítem Candidatos', () => {
  test.use({ storageState: estadoDe('sinPermiso') })

  test('las tres pantallas responden 403 (originales y /v2) y no abren la SPA', async ({ page, monitor }) => {
    monitor.permitir(/^403 GET \/(recruiting|v2)\//)
    const id = semilla().candidatos.completo!.id
    for (const ruta of ['/recruiting/candidatos', '/recruiting/candidatos/nuevo', `/recruiting/candidatos/${id}`, '/v2/recruiting/candidatos', '/v2/recruiting/candidatos/nuevo', `/v2/recruiting/candidatos/${id}`]) {
      const r = await page.goto(ruta)
      expect(r?.status(), ruta).toBe(403)
      await expect(page.getByTestId('indicador-registros'), ruta).toHaveCount(0)
    }
  })

  test('el backend también niega los datos (la protección no es solo de la interfaz)', async ({ page, monitor }) => {
    monitor.permitir(/^403 GET \/api\/v1\/recruiting/)
    const r = await page.request.get('/api/v1/recruiting/candidatos?pagina=1&por_pagina=20')
    expect(r.status()).toBe(403)
  })

  test('el menú no ofrece «Candidatos»', async ({ page }) => {
    await page.goto('/')
    await page.locator('aside').getByText('Recruiting', { exact: true }).first().click().catch(() => undefined)
    await expect(page.locator('aside a', { hasText: 'Candidatos' })).toHaveCount(0)
  })
})

test.describe('sin sesión', () => {
  test.use({ storageState: { cookies: [], origins: [] } })

  test('las URLs llevan al login', async ({ page }) => {
    const id = semilla().candidatos.completo!.id
    for (const ruta of ['/recruiting/candidatos', '/recruiting/candidatos/nuevo', `/recruiting/candidatos/${id}`, '/v2/recruiting/candidatos', '/v2/recruiting/candidatos/nuevo', `/v2/recruiting/candidatos/${id}`]) {
      await page.goto(ruta)
      await expect(page, ruta).toHaveURL(/\/login/)
    }
  })
})

test.describe('usuario del grupo EXTERNOS', () => {
  test.use({ storageState: estadoDe('externo') })

  test('entra a la grilla pero sin las acciones restringidas (eliminar, cargas y asignar)', async ({ page }) => {
    await page.goto('/recruiting/candidatos')
    await expect(page.getByTestId('indicador-registros')).toBeVisible()
    await expect(page.getByTestId('abrir-carga-individual')).toHaveCount(0)
    await expect(page.getByTestId('abrir-carga-masiva')).toHaveCount(0)
    await expect(page.getByTestId('accion-eliminar')).toHaveCount(0)
    await expect(page.getByTestId('accion-asignar')).toHaveCount(0)
    await expect(page.getByTestId('nuevo-candidato')).toBeVisible()
  })
})
