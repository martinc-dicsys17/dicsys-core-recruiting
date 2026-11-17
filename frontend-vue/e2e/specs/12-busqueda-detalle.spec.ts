import type { Page } from '@playwright/test'

import { ADMIN, ClienteApi } from '../api'
import { crearPdf, textoCv } from '../archivos'
import { estadoDe, expect, test } from '../fixtures'
import { candidatoEnBase } from '../helpers'

/**
 * Ficha de una Búsqueda. Criterio legacy (oportunidad_detalle.html): lectura con todas las tarjetas, edición donde solo
 * Descripción y Skills deseadas se guardan (el resto se ve bloqueado), «Volver» con ?volver=, reclutador y usuario
 * externo (con confirmaciones nativas), candidatos del proceso, Smart Matching (desglose y «Postular a Búsqueda»),
 * búsqueda Ganada de solo consulta y acceso sin permiso. Los datos se crean con el backend dentro de la prueba; el
 * resultado se comprueba también contra el backend.
 */
const SUFIJO = Date.now().toString(36)
const TITULO = `Ficha E2E ${SUFIJO}`
const TITULO_GANADA = `Ficha Ganada E2E ${SUFIJO}`
const EMAIL_SUGERIDO = `sugerido.${SUFIJO}@example.com`

interface Creada {
  id: string
}
let api: ClienteApi
let busqueda: Creada
let ganada: Creada
let sugerido: { id: string }

test.beforeAll(async () => {
  api = await ClienteApi.ingresar(ADMIN.email, ADMIN.password)
  const alta = (titulo: string) =>
    api.post<Creada>('/recruiting/oportunidades', {
      cliente: 'Cliente Ficha E2E',
      titulo,
      estado: 'Abierta',
      seniority: 'Semi Senior',
      modalidad: 'Hibrido',
      vacantes: 2,
      skills: ['Python', 'PostgreSQL', 'Redis'],
      habilidades: [],
      skills_deseadas: ['Docker'],
      descripcion: 'Equipo de plataforma',
    })
  busqueda = await alta(TITULO)
  ganada = await alta(TITULO_GANADA)
  await api.put(`/recruiting/oportunidades/${ganada.id}`, { estado: 'Ganada' })
  sugerido = await api.post<{ id: string }>('/recruiting/candidatos', {
    nombre: 'Sara',
    apellido: `Sugerida${SUFIJO}`,
    email: EMAIL_SUGERIDO,
    seniority: 'Semi Senior',
    skills: ['Python', 'PostgreSQL'],
    habilidades: [],
  })
})

const abrir = async (page: Page, id: string, query = '') => {
  await page.goto(`/recruiting/oportunidades/${id}${query}`)
  await expect(page.getByTestId('busqueda-titulo').or(page.getByTestId('detalle-error')).or(page.locator('h1', { hasText: 'Editar Búsqueda' }))).toBeVisible()
}
const dato = (page: Page, etiqueta: string) => page.getByText(etiqueta, { exact: true }).first().locator('xpath=following-sibling::*[1]')
const buscar = (id: string) => api.get<Record<string, unknown>>(`/recruiting/oportunidades/${id}`)

test.describe('acceso', () => {
  test.use({ storageState: estadoDe('autorizado') })

  test('la URL original redirige a la pantalla Vue conservando los parámetros', async ({ page }) => {
    await page.goto(`/recruiting/oportunidades/${busqueda.id}?volver=%2Frecruiting%2Foportunidades%3Festado%3Dtodos`)
    await expect(page).toHaveURL(new RegExp(`/v2/recruiting/oportunidades/${busqueda.id}\\?volver=`))
    await expect(page.getByTestId('busqueda-titulo')).toHaveText(TITULO)
  })

  test('«/editar» abre la misma ficha en modo edición', async ({ page }) => {
    await page.goto(`/recruiting/oportunidades/${busqueda.id}/editar`)
    await expect(page).toHaveURL(new RegExp(`/v2/recruiting/oportunidades/${busqueda.id}\\?edit=true`))
    await expect(page.getByRole('heading', { name: 'Editar Búsqueda' })).toBeVisible()
    await expect(page.getByText('Modo Edición')).toBeVisible()
  })

  test('acceso directo a /v2 (con permiso: abre)', async ({ page }) => {
    const r = await page.goto(`/v2/recruiting/oportunidades/${busqueda.id}`)
    expect(r?.status()).toBe(200)
    await expect(page.getByTestId('busqueda-titulo')).toBeVisible()
  })
})

test.describe('búsqueda inexistente', () => {
  test.use({ storageState: estadoDe('autorizado') })

  test('vuelve al listado con el aviso «no existe o no fue encontrada»', async ({ page, monitor }) => {
    monitor.permitir(/^404 GET \/api\/v1\/recruiting\/oportunidades\//)
    await page.goto('/recruiting/oportunidades/00000000-0000-4000-8000-000000000000')
    await expect(page).toHaveURL(/\/v2\/recruiting\/oportunidades(\?|$)/)
    await expect(page.getByText('La búsqueda solicitada no existe o no fue encontrada.')).toBeVisible()
  })
})

test.describe('sin permiso', () => {
  test.use({ storageState: estadoDe('sinPermiso') })

  test('sin el ítem «recruiting.oportunidades» la ficha da 403', async ({ page, monitor }) => {
    monitor.permitir(/^403 GET \/(recruiting|v2)\//)
    const r = await page.goto(`/recruiting/oportunidades/${busqueda.id}`)
    expect(r?.status()).toBe(403)
  })
})

test.describe('usuario externo sin la búsqueda asignada', () => {
  test.use({ storageState: estadoDe('externo') })

  // La semilla da al grupo EXTERNOS solo «Candidatos»; para llegar a la pantalla necesita el ítem de Búsquedas (en uso
  // real lo tiene). Se agrega durante esta prueba y se devuelve el grupo a como estaba.
  let grupoExternos = ''
  const permisosExternos = (...modulos: string[]) => ({ permisos: modulos.map((modulo) => ({ modulo, tiene_acceso: true })) })
  test.beforeAll(async () => {
    const { grupos } = await api.get<{ grupos: { id: string; nombre: string }[] }>('/permisos/grupos')
    grupoExternos = grupos.find((g) => g.nombre === 'EXTERNOS')!.id
    await api.put(`/permisos/grupos/${grupoExternos}/permisos`, permisosExternos('recruiting', 'recruiting.candidatos', 'recruiting.oportunidades'))
  })
  test.afterAll(async () => {
    await api.put(`/permisos/grupos/${grupoExternos}/permisos`, permisosExternos('recruiting', 'recruiting.candidatos'))
  })

  test('la API responde 403 y, como la pantalla anterior, vuelve al listado con el aviso', async ({ page, monitor }) => {
    monitor.permitir(/^403 GET \/(recruiting|v2|api\/v1\/recruiting)\//)
    await page.goto(`/v2/recruiting/oportunidades/${busqueda.id}`)
    await expect(page).toHaveURL(/\/v2\/recruiting\/oportunidades(\?|$)/)
    await expect(page.getByText('No tenés acceso a esta búsqueda: no la tenés asignada.')).toBeVisible()
    await expect(page.getByTestId('indicador-registros')).toBeVisible()
  })
})

test.describe('lectura', () => {
  test.use({ storageState: estadoDe('autorizado') })

  test('muestra las tarjetas con los datos de la búsqueda', async ({ page }) => {
    await abrir(page, busqueda.id)
    await expect(page.getByTestId('busqueda-titulo')).toHaveText(TITULO)
    await expect(page.locator('h1 + span')).toHaveText('Abierta')
    await expect(page.getByText('Cliente Ficha E2E ·')).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Datos Generales y Cliente' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Asignación del Proceso' })).toBeVisible()
    await expect(dato(page, 'Seniority Solicitado')).toHaveText('Semi Senior')
    await expect(dato(page, 'Modalidad de Trabajo')).toHaveText('Híbrido')
    await expect(dato(page, 'Vacantes')).toHaveText('2 posición(es)')
    await expect(dato(page, 'Rango Salarial Pretendido')).toHaveText('A convenir')
    await expect(page.getByTestId('descripcion-busqueda')).toContainText('Equipo de plataforma')
    await expect(page.getByText('PostgreSQL', { exact: true }).first()).toBeVisible()
    await expect(page.getByText('Docker', { exact: true }).first()).toBeVisible()
    await expect(dato(page, 'Estado Operativo')).toContainText('Abierta')
    await expect(page.getByText('Sin asignar').first()).toBeVisible()
    await expect(page.getByText('Los tiempos de apertura se contabilizan')).toBeVisible()
  })

  test('«Volver» regresa al origen (?volver=) o, sin él, al listado de Búsquedas', async ({ page }) => {
    await abrir(page, busqueda.id, '?volver=%2Frecruiting%2Foportunidades%3Festado%3Dtodos')
    await expect(page.getByTestId('volver')).toHaveAttribute('href', '/recruiting/oportunidades?estado=todos')
    await abrir(page, busqueda.id, '?volver=https%3A%2F%2Fexterno.example.com')
    await expect(page.getByTestId('volver')).toHaveAttribute('href', '/recruiting/oportunidades')
    await abrir(page, busqueda.id)
    await expect(page.getByTestId('volver')).toHaveAttribute('href', '/recruiting/oportunidades')
  })

  test('sin candidatos asignados muestra el estado vacío', async ({ page }) => {
    await abrir(page, busqueda.id)
    await expect(page.getByTestId('asignados-vacio')).toContainText('No hay candidatos asignados a esta búsqueda todavía')
  })
})

test.describe('edición', () => {
  test.use({ storageState: estadoDe('autorizado') })

  test('solo Descripción y Skills deseadas se editan; el resto queda bloqueado', async ({ page }) => {
    await abrir(page, busqueda.id)
    await page.getByTestId('editar').click()
    await expect(page.getByText('Modo Edición')).toBeVisible()
    const habilitados = page.locator('input:not([disabled]):not([type=file]), select:not([disabled]), textarea:not([disabled])')
    // Descripción, campo para tipear una skill deseada
    await expect(page.getByTestId('descripcion-editar')).toBeEnabled()
    await expect(page.getByTestId('selector-deseadas').locator('input')).toBeEnabled()
    await expect(page.locator('input[placeholder="Ej: Senior Data Engineer"]')).toBeDisabled()
    await expect(page.getByTestId('selector-skills').locator('input')).toBeDisabled()
    expect(await habilitados.count()).toBeGreaterThanOrEqual(2)
  })

  test('«Cancelar» descarta los cambios sin llamar al backend', async ({ page, monitor }) => {
    await abrir(page, busqueda.id)
    await page.getByTestId('editar').click()
    await page.getByTestId('descripcion-editar').fill('Texto que se descarta')
    await page.getByTestId('cancelar-edicion').click()
    await expect(page.getByTestId('descripcion-busqueda')).toContainText('Equipo de plataforma')
    expect(monitor.mutacionesDe(/PUT .*\/oportunidades\//)).toHaveLength(0)
  })

  test('«Guardar Cambios» manda solo descripción y skills deseadas y se refleja en el backend', async ({ page, monitor }) => {
    await abrir(page, busqueda.id)
    await page.getByTestId('editar').click()
    await page.getByTestId('descripcion-editar').fill('  Nueva descripcion E2E  ')
    const selector = page.getByTestId('selector-deseadas')
    await selector.locator('input').fill('Terraform')
    await selector.locator('input').press('Enter')
    await expect(selector.locator('span.inline-flex', { hasText: 'Terraform' })).toBeVisible()
    await selector.locator('span.inline-flex', { hasText: 'Docker' }).locator('button').click()
    await page.getByTestId('guardar-cambios').click()
    await expect(page.getByTestId('toast')).toHaveText('Búsqueda actualizada correctamente.')
    await expect(page.getByTestId('descripcion-busqueda')).toContainText('Nueva descripcion E2E')
    const puts = monitor.mutacionesDe(/PUT \/api\/v1\/recruiting\/oportunidades\//)
    expect(puts).toHaveLength(1)
    expect(JSON.parse(puts[0]!.cuerpo!)).toEqual({ skills_deseadas: ['Terraform'], descripcion: 'Nueva descripcion E2E' })
    const real = await buscar(busqueda.id)
    expect(real.descripcion).toBe('Nueva descripcion E2E')
    expect(real.skills_deseadas).toEqual(['Terraform'])
    expect(real.titulo).toBe(TITULO)
  })

  test('un botón del catálogo agrega y vuelve a quitar la skill deseada', async ({ page }) => {
    await abrir(page, busqueda.id)
    await page.getByTestId('editar').click()
    const selector = page.getByTestId('selector-deseadas')
    const opcion = selector.getByRole('button', { name: 'Python', exact: true })
    await expect(opcion).toBeVisible()
    await opcion.click()
    await expect(selector.locator('span.inline-flex', { hasText: 'Python' })).toBeVisible()
    await opcion.click()
    await expect(selector.locator('span.inline-flex', { hasText: 'Python' })).toHaveCount(0)
  })
})

test.describe('asignaciones (administrador)', () => {
  test.use({ storageState: estadoDe('admin') })

  test('usuario externo: asignar y quitar piden confirmación y se reflejan en el backend', async ({ page }) => {
    const externos = await api.get<{ id: string; nombre: string; email: string }[]>('/recruiting/externos-disponibles')
    test.skip(externos.length === 0, 'no hay usuarios en el grupo Externos')
    const ext = externos[0]!
    await abrir(page, busqueda.id)
    await expect(page.locator('#externo-asignado-nombre')).toHaveText('Sin asignar')
    await page.locator('#btn-gestionar-externo').click()
    await page.locator('#select-externo').selectOption(ext.id)
    await page.locator('#btn-guardar-externo').click()
    await expect(page.getByTestId('toast')).toHaveText('Usuario externo asignado correctamente.')
    await expect(page.locator('#externo-asignado-nombre')).toContainText(ext.email)
    expect((await buscar(busqueda.id)).externo_id).toBe(ext.id)

    // Quitar: se cancela la confirmación y no pasa nada; al aceptarla se quita.
    page.once('dialog', (d) => d.dismiss())
    await page.locator('#btn-quitar-externo').click()
    await expect(page.locator('#externo-asignado-nombre')).toContainText(ext.email)
    page.once('dialog', async (d) => {
      expect(d.message()).toContain('Se quitara la asignacion del usuario externo')
      await d.accept()
    })
    await page.locator('#btn-quitar-externo').click()
    await expect(page.getByTestId('toast')).toHaveText('Asignación del usuario externo quitada.')
    await expect(page.locator('#externo-asignado-nombre')).toHaveText('Sin asignar')
    expect((await buscar(busqueda.id)).externo_id).toBeNull()
  })

  test('reclutador: «Asignar» con la lista del catálogo y confirmación de guardado', async ({ page }) => {
    const reclutadores = await api.get<{ nombre: string }[]>('/recruiting/reclutadores')
    test.skip(reclutadores.length === 0, 'no hay reclutadores activos en el catálogo')
    const nombre = reclutadores[0]!.nombre
    await abrir(page, busqueda.id)
    await page.getByRole('button', { name: 'Asignar' }).first().click()
    await page.getByRole('button', { name: 'Guardar', exact: true }).click()
    await expect(page.getByTestId('toast')).toHaveText('Seleccioná un reclutador.')
    await page.locator('select').filter({ hasText: 'Seleccionar reclutador' }).selectOption(nombre)
    await page.getByRole('button', { name: 'Guardar', exact: true }).click()
    await expect(page.getByTestId('toast')).toHaveText('Reclutador asignado correctamente.')
    await expect(page.getByText(`Reclutador: ${nombre}`)).toBeVisible()
    expect((await buscar(busqueda.id)).recruiter_nombre).toBe(nombre)
  })
})

test.describe('candidatos del proceso y Smart Matching', () => {
  test.use({ storageState: estadoDe('autorizado') })

  test('lista los candidatos sugeridos con su porcentaje y el desglose del cálculo', async ({ page }) => {
    await abrir(page, busqueda.id)
    await expect(page.getByRole('heading', { name: 'Candidatos Sugeridos (Match de Skills)' })).toBeVisible()
    const fila = page.getByTestId('tabla-sugeridos').locator('tr', { hasText: `Sugerida${SUFIJO}` })
    await expect(fila).toHaveCount(1)
    await expect(fila.getByTestId('porcentaje-match')).toHaveText(/^\d+%\s*$/)
    await expect(fila.getByTestId('porcentaje-match')).toHaveAttribute('title', /DETALLE SMART MATCHING/)
    await expect(fila.getByRole('link', { name: /Sara/ })).toHaveAttribute('href', new RegExp(`^/recruiting/candidatos/${sugerido.id}\\?volver=%2Frecruiting%2Foportunidades%2F${busqueda.id}`))
    await fila.getByTestId('ver-desglose').click()
    const modal = page.getByTestId('modal-smart-matching')
    await expect(modal).toContainText('Cálculo de Smart Matching')
    await expect(modal).toContainText('Umbral mínimo requerido:')
    await expect(modal).toContainText('Fórmula de Cálculo:')
    await page.keyboard.press('Escape')
    await expect(modal).toHaveCount(0)
  })

  test('«Postular a Búsqueda»: suma el candidato al pipeline y pasa a «Candidatos Asignados»', async ({ page, monitor }) => {
    await abrir(page, busqueda.id)
    const fila = page.getByTestId('tabla-sugeridos').locator('tr', { hasText: `Sugerida${SUFIJO}` })
    // Si el match no llega al mínimo, el navegador pide confirmación (se acepta)
    page.on('dialog', (d) => void d.accept())
    await fila.getByTestId('postular').click()
    const asignado = page.getByTestId('tabla-asignados').locator('tr', { hasText: `Sugerida${SUFIJO}` })
    await expect(asignado).toHaveCount(1)
    await expect(asignado).toContainText('Candidato en proceso')
    await expect(page.getByTestId('tabla-sugeridos').locator('tr', { hasText: `Sugerida${SUFIJO}` })).toHaveCount(0)
    const posts = monitor.mutacionesDe(/POST \/api\/v1\/recruiting\/oportunidades\/.*\/candidatos$/)
    expect(posts).toHaveLength(1)
    expect(JSON.parse(posts[0]!.cuerpo!)).toMatchObject({ candidato_id: sugerido.id, etapa: 'Postulado', estado: 'En proceso' })
    const proceso = await api.get<{ candidato_id: string }[]>(`/recruiting/oportunidades/${busqueda.id}/candidatos`)
    expect(proceso.map((c) => c.candidato_id)).toContain(sugerido.id)
    // «Ver Ficha» lleva a la ficha del candidato conservando el origen
    await expect(asignado.getByTitle('Ver Ficha')).toHaveAttribute('href', new RegExp(`^/recruiting/candidatos/${sugerido.id}\\?volver=`))
    await expect(page.getByTestId('asignados-vacio')).toHaveCount(0)
  })

  test('postular sin llegar al mínimo pide confirmación y se puede cancelar', async ({ page, monitor }) => {
    const otro = await api.post<{ id: string }>('/recruiting/candidatos', {
      nombre: 'Bajo',
      apellido: `Match${SUFIJO}`,
      email: `bajo.${SUFIJO}@example.com`,
      seniority: 'Trainee',
      skills: ['Python'],
      habilidades: [],
    })
    await abrir(page, busqueda.id)
    const fila = page.getByTestId('tabla-sugeridos').locator('tr', { hasText: `Match${SUFIJO}` })
    const porcentaje = Number((await fila.getByTestId('porcentaje-match').innerText()).replace('%', ''))
    test.skip(porcentaje >= 50, 'el candidato de prueba llega al mínimo configurado')
    let mensaje = ''
    page.once('dialog', async (d) => {
      mensaje = d.message()
      await d.dismiss()
    })
    await fila.getByTestId('postular').click()
    await expect.poll(() => mensaje).toContain('¿Estás seguro de asignarlo aunque tiene menos de')
    expect(monitor.mutacionesDe(/POST .*\/oportunidades\/.*\/candidatos$/)).toHaveLength(0)
    const proceso = await api.get<{ candidato_id: string }[]>(`/recruiting/oportunidades/${busqueda.id}/candidatos`)
    expect(proceso.map((c) => c.candidato_id)).not.toContain(otro.id)
  })

  test('«Nuevo Candidato» y «Cargar CV» no aparecen para un usuario que no es externo', async ({ page }) => {
    await abrir(page, busqueda.id)
    await expect(page.getByTestId('cargar-cv-busqueda')).toHaveCount(0)
    await expect(page.getByTestId('nuevo-candidato-busqueda')).toHaveCount(0)
  })
})

test.describe('búsqueda Ganada', () => {
  test.use({ storageState: estadoDe('autorizado') })

  test('es de solo consulta: aviso, sin «Editar», sin Smart Matching ni acciones', async ({ page }) => {
    await abrir(page, ganada.id)
    await expect(page.getByTestId('aviso-busqueda-ganada')).toContainText('Búsqueda Ganada y cerrada')
    await expect(page.locator('h1 + span')).toHaveText('Ganada')
    await expect(page.getByTestId('editar')).toHaveCount(0)
    await expect(page.getByRole('heading', { name: 'Candidatos Sugeridos (Match de Skills)' })).toHaveCount(0)
    await expect(page.locator('#btn-gestionar-externo')).toHaveCount(0)
    await expect(page.getByRole('button', { name: 'Asignar' })).toHaveCount(0)
    await expect(page.getByTestId('volver')).toBeVisible()
  })

  test('el backend rechaza editarla (409)', async () => {
    const r = await api.pedir('PUT', `/recruiting/oportunidades/${ganada.id}`, { descripcion: 'x' }, [409])
    expect(r.estado).toBe(409)
  })
})

test.describe('usuario EXTERNO con la búsqueda asignada: carga de CV', () => {
  test.use({ storageState: estadoDe('externo') })

  // La semilla da al grupo EXTERNOS solo «Candidatos»: se le habilita «Búsquedas» durante estas pruebas y se restituye.
  // Los datos salen del propio backend: la búsqueda se crea y se asigna al usuario externo de la semilla por la API real.
  const EMAIL_CV = `cv.externo.${SUFIJO}@example.com`
  let grupoExternos = ''
  let asignada: Creada
  const permisosExternos = (...modulos: string[]) => ({ permisos: modulos.map((modulo) => ({ modulo, tiene_acceso: true })) })
  test.beforeAll(async () => {
    const { grupos } = await api.get<{ grupos: { id: string; nombre: string }[] }>('/permisos/grupos')
    grupoExternos = grupos.find((g) => g.nombre === 'EXTERNOS')!.id
    await api.put(`/permisos/grupos/${grupoExternos}/permisos`, permisosExternos('recruiting', 'recruiting.candidatos', 'recruiting.oportunidades'))
    asignada = await api.post<Creada>('/recruiting/oportunidades', {
      cliente: 'Cliente Externo CV E2E',
      titulo: `Externo CV ${SUFIJO}`,
      estado: 'Abierta',
      vacantes: 1,
      skills: ['Python'],
      habilidades: [],
      skills_deseadas: [],
    })
    const externos = await api.get<{ id: string; email: string }[]>('/recruiting/externos-disponibles')
    const externo = externos.find((u) => u.email === 'externo.e2e@dicsys.com')!
    await api.put(`/recruiting/oportunidades/${asignada.id}/externo`, { externo_id: externo.id })
  })
  test.afterAll(async () => {
    await api.put(`/permisos/grupos/${grupoExternos}/permisos`, permisosExternos('recruiting', 'recruiting.candidatos'))
  })

  test('ve «Nuevo Candidato» y «Cargar CV» y no ve Smart Matching', async ({ page }) => {
    await abrir(page, asignada.id)
    await expect(page.getByTestId('cargar-cv-busqueda')).toBeVisible()
    await expect(page.getByTestId('nuevo-candidato-busqueda')).toBeVisible()
    await expect(page.getByTestId('tabla-sugeridos')).toHaveCount(0)
  })

  test('un CV válido crea el candidato, lo suma a la búsqueda y avisa', async ({ page, monitor }) => {
    await abrir(page, asignada.id)
    await page.getByTestId('input-cargar-cv-busqueda').setInputFiles({
      name: 'cv-externo.pdf',
      mimeType: 'application/pdf',
      buffer: crearPdf(textoCv({ nombre: 'Elena', apellido: 'Externa', email: EMAIL_CV, telefono: '+5493515551234' })),
    })
    await expect(page.getByTestId('toast')).toBeVisible()
    expect(monitor.mutacionesDe(/POST \/recruiting\/oportunidades\/.*\/cargar-cv$/)).toHaveLength(1)
    // El candidato existe en la base y quedó en el proceso de la búsqueda (comprobado con la API como administrador)
    const fila = candidatoEnBase(EMAIL_CV, 'id, nombre, apellido')!
    expect(fila.slice(1)).toEqual(['Elena', 'Externa'])
    const proceso = await api.get<{ candidato_id: string }[]>(`/recruiting/oportunidades/${asignada.id}/candidatos`)
    expect(proceso.map((c) => c.candidato_id)).toContain(fila[0])
    await expect(page.getByTestId('tabla-asignados').locator('tbody tr')).toHaveCount(1)
  })

  test('un formato no admitido lo rechaza el servidor, avisa el error y no crea nada', async ({ page, monitor }) => {
    monitor.permitir(/^400 POST \/recruiting\/oportunidades\/.*\/cargar-cv/)
    await abrir(page, asignada.id)
    await page.getByTestId('input-cargar-cv-busqueda').setInputFiles({ name: 'cv.txt', mimeType: 'text/plain', buffer: Buffer.from('x') })
    await expect(page.getByTestId('toast')).toContainText(/formato|Formato|admit|permit/)
    expect(candidatoEnBase('x')).toBeNull()
  })
})
