import { ADMIN, ClienteApi } from '../api'
import { estadoDe, expect, semilla, test } from '../fixtures'

/**
 * Nueva Búsqueda (alta). Criterio legacy (oportunidad_form.html): obligatorios Título, Cliente y Reclutador; valores
 * iniciales Efectiva / Alta / Senior / Híbrido, 1 vacante y primer reclutador del catálogo; rango salarial con formato
 * «$ 2.000.000 - $ 3.500.000» y de menor a mayor; chips de skills, competencias y skills deseadas (catálogo, manual y
 * quitar); alta por POST /oportunidades; al crear vuelve al listado de búsquedas.
 */
const titulo = (marca: string) => `Busqueda E2E ${marca} ${Date.now()}`

interface Pagina {
  items: { id: string; titulo: string; cliente: string; estado: string; tipo: string; puesto?: string | null; skills: string[]; habilidades: string[]; skills_deseadas: string[]; vacantes: number; rango?: string | null; prioridad: string; seniority: string; modalidad: string; recruiter_nombre?: string | null; lider_nombre?: string | null; descripcion?: string | null }[]
}
async function buscarEnApi(texto: string) {
  const admin = await ClienteApi.ingresar(ADMIN.email, ADMIN.password)
  const r = await admin.get<Pagina>(`/recruiting/oportunidades?busqueda=${encodeURIComponent(texto)}&estado=todos&tipo=Todas`)
  return r.items
}

type Pg = import('@playwright/test').Page
const abrir = async (page: Pg) => {
  await page.goto('/recruiting/oportunidades/nueva')
  await expect(page.getByTestId('guardar')).toBeVisible()
  await expect(page.locator('#reclutador option')).not.toHaveCount(1) // catálogo de reclutadores cargado
}

test.describe('usuario autorizado', () => {
  test.use({ storageState: estadoDe('autorizado') })

  test('la URL original redirige a la pantalla Vue y el acceso directo a /v2 abre', async ({ page }) => {
    await page.goto('/recruiting/oportunidades/nueva')
    await expect(page).toHaveURL(/\/v2\/recruiting\/oportunidades\/nueva$/)
    await expect(page.getByRole('heading', { name: 'Nueva Oportunidad' })).toBeVisible()
    const r = await page.goto('/v2/recruiting/oportunidades/nueva')
    expect(r?.status()).toBe(200)
    await expect(page.getByTestId('guardar')).toBeVisible()
  })

  test('valores iniciales y catálogos', async ({ page }) => {
    await abrir(page)
    await expect(page.locator('#titulo')).toHaveValue('')
    await expect(page.locator('#cliente')).toHaveValue('')
    await expect(page.locator('#tipo')).toHaveValue('Efectiva')
    await expect(page.locator('#prioridad')).toHaveValue('Alta')
    await expect(page.locator('#seniority')).toHaveValue('Senior')
    await expect(page.locator('#modalidad')).toHaveValue('Hibrido')
    await expect(page.locator('#vacantes')).toHaveValue('1')
    await expect(page.locator('#puesto')).toHaveValue('')
    await expect(page.locator('#lider')).toHaveValue('')
    await expect(page.locator('#fecha-creacion')).toBeDisabled()
    await expect(page.getByTestId('guardar')).toHaveText('Crear Oportunidad')
    // Se preselecciona el primer reclutador del catálogo
    const primero = await page.locator('#reclutador option').nth(1).innerText()
    await expect(page.locator('#reclutador')).toHaveValue(primero)
    // Opciones fijas
    expect(await page.locator('#tipo option').allInnerTexts()).toEqual(['Efectiva', 'Potencial'])
    expect(await page.locator('#prioridad option').allInnerTexts()).toEqual(['Crítica', 'Alta', 'Media', 'Baja'])
    expect(await page.locator('#seniority option').allInnerTexts()).toEqual(['Junior', 'Semi Sr', 'Senior', 'Lead'])
    expect(await page.locator('#modalidad option').allInnerTexts()).toEqual(['Remoto', 'Híbrido', 'Presencial'])
    // Catálogos reales
    expect(await page.locator('#puesto option').count()).toBeGreaterThan(5)
    expect(await page.getByTestId('skills-catalogo').getByRole('button').count()).toBeGreaterThan(20)
    expect(await page.getByTestId('habilidades-catalogo').getByRole('button').count()).toBeGreaterThan(5)
    await expect(page.getByTestId('skills-elegidas')).toContainText('Ninguna tecnología seleccionada')
    await expect(page.getByTestId('habilidades-elegidas')).toContainText('Ninguna habilidad o competencia seleccionada')
    await expect(page.getByTestId('skills-deseadas-elegidas')).toContainText('Ninguna skill deseada seleccionada')
  })

  test('chips: alternar del catálogo, agregar manual (sin repetir) y quitar', async ({ page }) => {
    await abrir(page)
    const catalogo = page.getByTestId('skills-catalogo').getByRole('button')
    const nombre = (await catalogo.first().innerText()).trim()
    await catalogo.first().click()
    await expect(page.getByTestId('skills-elegidas')).toContainText(nombre)
    await catalogo.first().click() // alterna: la quita
    await expect(page.getByTestId('skills-elegidas')).toContainText('Ninguna tecnología seleccionada')

    await page.locator('#skills').fill('Tecnologia Manual E2E')
    await page.locator('#skills').press('Enter') // Enter agrega y no envía el formulario
    await expect(page.getByTestId('skills-elegidas')).toContainText('Tecnologia Manual E2E')
    await expect(page.locator('#skills')).toHaveValue('')
    await page.locator('#skills').fill('Tecnologia Manual E2E')
    await page.getByRole('button', { name: '+ Agregar Tecnología' }).click() // repetida: no se agrega y el campo queda
    await expect(page.getByTestId('skills-elegidas').getByText('Tecnologia Manual E2E')).toHaveCount(1)
    await expect(page.locator('#skills')).toHaveValue('Tecnologia Manual E2E')
    await page.getByRole('button', { name: 'Quitar Tecnologia Manual E2E' }).click()
    await expect(page.getByTestId('skills-elegidas')).toContainText('Ninguna tecnología seleccionada')

    await page.locator('#habilidades').fill('Competencia Manual E2E')
    await page.getByRole('button', { name: '+ Agregar Habilidad' }).click()
    await expect(page.getByTestId('habilidades-elegidas')).toContainText('Competencia Manual E2E')
    await page.locator('#skills-deseadas').fill('Deseada Manual E2E')
    await page.getByRole('button', { name: '+ Agregar Skill' }).click()
    await expect(page.getByTestId('skills-deseadas-elegidas')).toContainText('Deseada Manual E2E')
    // Las deseadas son independientes de las requeridas
    await expect(page.getByTestId('skills-elegidas')).toContainText('Ninguna tecnología seleccionada')
  })

  test('rango salarial: formato automático y validaciones', async ({ page }) => {
    await abrir(page)
    const rango = page.getByTestId('rango-salarial')
    await rango.fill('20000003500000')
    await expect(rango).toHaveValue('$ 20.000.003.500.000')
    await rango.fill('2000000-3500000')
    await expect(rango).toHaveValue('$ 2.000.000 - $ 3.500.000')
    await expect(page.getByTestId('rango-salarial-error')).toHaveCount(0)
    await rango.fill('3500000-2000000')
    await expect(page.getByTestId('rango-salarial-error')).toContainText('El rango salarial debe ser de menor a mayor')
    await rango.fill('2000000')
    await expect(page.getByTestId('rango-salarial-error')).toHaveCount(0) // sin tocar: aún no avisa
    await rango.blur()
    await expect(page.getByTestId('rango-salarial-error')).toContainText('Ingresá ambos importes del rango salarial')
  })

  test('campos obligatorios: el navegador impide enviar sin título, cliente o reclutador', async ({ page, monitor }) => {
    await abrir(page)
    await page.getByTestId('guardar').click()
    await expect(page.locator('#titulo')).toHaveJSProperty('validity.valueMissing', true)
    await page.locator('#titulo').fill('Solo titulo')
    await page.getByTestId('guardar').click()
    await expect(page.locator('#cliente')).toHaveJSProperty('validity.valueMissing', true)
    expect(monitor.mutacionesDe(/POST .*oportunidades/)).toHaveLength(0)
  })

  test('título solo con espacios: avisa y no envía', async ({ page, monitor }) => {
    await abrir(page)
    await page.locator('#titulo').fill('   ')
    await page.locator('#cliente').fill('Cliente E2E')
    await page.getByTestId('guardar').click()
    await expect(page.getByTestId('error-general')).toHaveText('Por favor ingresá el título de la posición.')
    await page.locator('#titulo').fill('Con titulo')
    await page.locator('#cliente').fill('   ')
    await page.getByTestId('guardar').click()
    await expect(page.getByTestId('error-general')).toHaveText('Por favor seleccioná el cliente.')
    expect(monitor.mutacionesDe(/POST .*oportunidades/)).toHaveLength(0)
  })

  test('rango inválido al guardar: muestra el error y no envía', async ({ page, monitor }) => {
    await abrir(page)
    await page.locator('#titulo').fill(titulo('rango'))
    await page.locator('#cliente').fill('Cliente E2E')
    await page.getByTestId('rango-salarial').fill('3500000-2000000')
    await page.getByTestId('guardar').click()
    await expect(page.getByTestId('error-general')).toContainText('El rango salarial debe ser de menor a mayor')
    expect(monitor.mutacionesDe(/POST .*oportunidades/)).toHaveLength(0)
  })

  test('alta mínima: crea la búsqueda con los valores iniciales y vuelve al listado', async ({ page, monitor }) => {
    const t = titulo('minima')
    await abrir(page)
    await page.locator('#titulo').fill(t)
    await page.locator('#cliente').fill('Cliente E2E')
    const reclutador = await page.locator('#reclutador').inputValue()
    await page.getByTestId('guardar').click()
    await expect(page.getByText('Oportunidad creada exitosamente.')).toBeVisible()
    await expect(page).toHaveURL(/\/recruiting\/oportunidades/)

    const cuerpo = JSON.parse(monitor.mutacionesDe(/POST .*\/oportunidades$/)[0]?.cuerpo ?? '{}')
    expect(cuerpo).toMatchObject({ titulo: t, cliente: 'Cliente E2E', estado: 'Abierta', tipo: 'Efectiva', prioridad: 'Alta', seniority: 'Senior', modalidad: 'Hibrido', vacantes: 1, recruiter_nombre: reclutador, lider_nombre: null, descripcion: null, skills: [], habilidades: [], skills_deseadas: [] })
    expect(cuerpo).not.toHaveProperty('puesto')
    expect(cuerpo).not.toHaveProperty('rango')

    const [creada] = await buscarEnApi(t)
    expect(creada).toMatchObject({ titulo: t, cliente: 'Cliente E2E', estado: 'Abierta', tipo: 'Efectiva', vacantes: 1, recruiter_nombre: reclutador })
  })

  test('alta completa: todos los campos viajan y se guardan', async ({ page }) => {
    const t = titulo('completa')
    await abrir(page)
    await page.locator('#titulo').fill(`  ${t}  `)
    await page.locator('#tipo').selectOption('Potencial')
    await page.locator('#puesto').selectOption({ index: 1 })
    const puesto = await page.locator('#puesto').inputValue()
    await page.locator('#cliente').fill('Cliente Completo E2E')
    await page.locator('#lider').selectOption({ index: 1 })
    const lider = await page.locator('#lider').inputValue()
    await page.locator('#reclutador').selectOption({ index: 1 })
    const reclutador = await page.locator('#reclutador').inputValue()
    await page.locator('#vacantes').fill('3')
    await page.locator('#prioridad').selectOption('Critica')
    await page.locator('#seniority').selectOption('Lead')
    await page.locator('#modalidad').selectOption('Presencial')
    await page.getByTestId('rango-salarial').fill('2000000-3500000')
    await page.locator('#descripcion').fill('  Descripcion E2E  ')
    await page.getByTestId('skills-catalogo').getByRole('button').first().click()
    const skill = (await page.getByTestId('skills-catalogo').getByRole('button').first().innerText()).trim()
    await page.getByTestId('habilidades-catalogo').getByRole('button').first().click()
    const habilidad = (await page.getByTestId('habilidades-catalogo').getByRole('button').first().innerText()).trim()
    await page.locator('#skills-deseadas').fill('Deseada E2E')
    await page.locator('#skills-deseadas').press('Enter')

    await page.getByTestId('guardar').click()
    await expect(page.getByText('Oportunidad creada exitosamente.')).toBeVisible()
    await expect(page).toHaveURL(/\/recruiting\/oportunidades/)

    const [creada] = await buscarEnApi(t)
    expect(creada).toMatchObject({ titulo: t, tipo: 'Potencial', puesto, cliente: 'Cliente Completo E2E', lider_nombre: lider, recruiter_nombre: reclutador, vacantes: 3, prioridad: 'Critica', seniority: 'Lead', modalidad: 'Presencial', rango: '$ 2.000.000 - $ 3.500.000', descripcion: 'Descripcion E2E' })
    expect(creada?.skills).toEqual([skill])
    expect(creada?.habilidades).toEqual([habilidad])
    expect(creada?.skills_deseadas).toEqual(['Deseada E2E'])
  })

  test('error del backend (título repetido para el cliente): lo muestra y sigue en el formulario', async ({ page, monitor }) => {
    monitor.permitir(/400 POST \/api\/v1\/recruiting\/oportunidades/)
    const existente = semilla().busquedas.python!.titulo
    await abrir(page)
    await page.locator('#titulo').fill(existente)
    await page.locator('#cliente').fill('Cliente E2E')
    await page.getByTestId('guardar').click()
    await expect(page.getByTestId('error-general')).toBeVisible()
    await expect(page.getByTestId('error-general')).not.toHaveText('')
    await expect(page).toHaveURL(/\/v2\/recruiting\/oportunidades\/nueva$/)
    await expect(page.getByTestId('guardar')).toBeEnabled()
    await expect(page.locator('#titulo')).toHaveValue(existente) // conserva lo escrito
  })

  test('Volver y Cancelar llevan al listado de búsquedas', async ({ page }) => {
    await abrir(page)
    await page.getByTestId('volver').click()
    await expect(page).toHaveURL(/\/recruiting\/oportunidades$/)
    await abrir(page)
    await page.getByTestId('cancelar').click()
    await expect(page).toHaveURL(/\/recruiting\/oportunidades$/)
  })
})

test.describe('usuario con acceso a Búsquedas pero sin permiso de crear (grupo EXTERNOS)', () => {
  test.use({ storageState: estadoDe('externo') })

  // La semilla da al grupo EXTERNOS solo «Candidatos»; se le habilita «Búsquedas» durante estas pruebas y se restituye.
  let admin: ClienteApi
  let grupoExternos = ''
  const permisosExternos = (...modulos: string[]) => ({ permisos: modulos.map((modulo) => ({ modulo, tiene_acceso: true })) })
  test.beforeAll(async () => {
    admin = await ClienteApi.ingresar(ADMIN.email, ADMIN.password)
    const { grupos } = await admin.get<{ grupos: { id: string; nombre: string }[] }>('/permisos/grupos')
    grupoExternos = grupos.find((g) => g.nombre === 'EXTERNOS')!.id
    await admin.put(`/permisos/grupos/${grupoExternos}/permisos`, permisosExternos('recruiting', 'recruiting.candidatos', 'recruiting.oportunidades'))
  })
  test.afterAll(async () => {
    await admin.put(`/permisos/grupos/${grupoExternos}/permisos`, permisosExternos('recruiting', 'recruiting.candidatos'))
  })

  test('el alta vuelve al listado con el aviso «No tenés permisos para crear búsquedas.» y sin el botón «+ Búsqueda»', async ({ page }) => {
    await page.goto('/recruiting/oportunidades/nueva')
    await expect(page).toHaveURL(/\/v2\/recruiting\/oportunidades(\?|$)/)
    await expect(page.getByText('No tenés permisos para crear búsquedas.')).toBeVisible()
    await expect(page.getByTestId('indicador-registros')).toBeVisible()
    await expect(page.getByTestId('nueva-busqueda')).toHaveCount(0)
  })
})

test.describe('usuario sin el permiso de Búsquedas', () => {
  test.use({ storageState: estadoDe('sinPermiso') })

  test('no puede abrir el alta (ni por la URL original ni por /v2)', async ({ page, monitor }) => {
    monitor.permitir(/403/)
    for (const ruta of ['/recruiting/oportunidades/nueva', '/v2/recruiting/oportunidades/nueva']) {
      const r = await page.goto(ruta)
      expect(r?.status(), ruta).toBe(403)
      await expect(page.getByTestId('guardar'), ruta).toHaveCount(0)
    }
  })
})

test.describe('sin sesión', () => {
  test.use({ storageState: { cookies: [], origins: [] } })

  test('lleva al login', async ({ page }) => {
    await page.goto('/v2/recruiting/oportunidades/nueva')
    await expect(page).toHaveURL(/\/login/)
  })
})
