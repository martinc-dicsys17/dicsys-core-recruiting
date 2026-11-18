import type { Locator, Page } from '@playwright/test'

import { ADMIN, ClienteApi } from '../api'
import { crearPdf } from '../archivos'
import { estadoDe, expect, test } from '../fixtures'
import { FILAS, abrirGrilla } from '../helpers'

/**
 * Circuito completo de Recruiting después de migrar Pipeline a Vue, hecho por la interfaz como lo haría un reclutador:
 * alta de dos búsquedas y cuatro candidatos, incorporación de candidatos por los tres caminos reales (grilla de
 * Candidatos, Smart Matching de la ficha y «Agregar Candidato» del Pipeline), recorrido del embudo completo con los tres
 * saltos permitidos, pretensión salarial, adjuntos, descarte, reingreso e Ingreso que gana y cierra la búsqueda.
 *
 * Criterio: las reglas del legacy (pipeline.html, candidatos.html, oportunidad_*.html) y del backend
 * (PipelineService._mover). Cada operación se comprueba en la interfaz y además contra el backend. La API solo prepara un
 * dato auxiliar (un candidato de otro usuario, para el filtro «Propios») y lee lo persistido; nunca simula una acción
 * que se está probando. Los datos son ficticios y únicos por corrida; la base E2E vive en tmpfs y se borra al bajar el
 * stack (globalTeardown).
 */
test.use({ storageState: estadoDe('autorizado') })
test.describe.configure({ mode: 'serial' })

const S = Date.now().toString(36)
const CLIENTE = 'Cliente Circuito E2E'
const B1 = `Circuito Principal E2E ${S}`
const B2 = `Circuito Ingreso E2E ${S}`
/**
 * Las búsquedas del circuito piden solo esta skill propia de la corrida (los candidatos del circuito la tienen, además de
 * Python). Un candidato sin ninguna skill en común queda afuera de Smart Matching y de la elegibilidad, sin importar su
 * seniority: así Smart Matching (que devuelve los 15 mejores) siempre incluye a Bruno, y ningún candidato de otros specs
 * (por ejemplo «Elisa Elegible» del 05, con Python) resulta elegible para estas búsquedas.
 */
const SKILL = `CircuitoE2E${S}`
const ETAPAS = [
  'Candidato',
  'Screening',
  'Entrevista RRHH',
  'Entrevista Líder Dicsys',
  'Validación Administración',
  'Entrevista Cliente',
  'Oferta',
  'Examen Médico Preocupacional',
  'Ingreso',
  'Descartados',
] as const

interface Cand {
  nombre: string
  apellido: string
  email: string
  id?: string
}
const C: Record<'ana' | 'bruno' | 'carla' | 'dora', Cand> = {
  ana: { nombre: 'Ana', apellido: `Avance${S}`, email: `ana.avance.${S}@example.com` },
  bruno: { nombre: 'Bruno', apellido: `Reingreso${S}`, email: `bruno.reingreso.${S}@example.com` },
  carla: { nombre: 'Carla', apellido: `Ingreso${S}`, email: `carla.ingreso.${S}@example.com` },
  dora: { nombre: 'Dora', apellido: `Cierre${S}`, email: `dora.cierre.${S}@example.com` },
}
const completo = (c: Cand) => `${c.nombre} ${c.apellido}`
const OTRO = { nombre: 'Otro', apellido: `Admin${S}`, email: `otro.admin.${S}@example.com`, id: '' }

let api: ClienteApi
const ids = { b1: '', b2: '' }
/** Etapa esperada de cada candidato en cada búsqueda (modelo para los contadores). */
const modelo: Record<string, Record<string, string>> = { b1: {}, b2: {} }

interface FilaApi {
  candidato_id: string
  etapa_actual: string
  estado: string
  feedback_etapa: string | null
  motivo_descarte: string | null
  pretension_salarial_bruta_ars: number | null
}
const filasApi = (b: string) => api.get<FilaApi[]>(`/recruiting/oportunidades/${b}/pipeline-candidatos`)
const enBackend = async (b: string, c: Cand) => (await filasApi(b)).find((f) => f.candidato_id === c.id)!
const buscarBusqueda = async (titulo: string) =>
  (await api.get<{ items: Record<string, unknown>[] }>(`/recruiting/oportunidades?busqueda=${encodeURIComponent(titulo)}&estado=todos&tipo=Todas`)).items

test.beforeAll(async () => {
  api = await ClienteApi.ingresar(ADMIN.email, ADMIN.password)
})

// ---- Helpers de interfaz ----------------------------------------------------------------------------------------

const fila = (page: Page, c: Cand) => page.getByTestId('fila-candidato').filter({ hasText: completo(c) })
const toast = (page: Page) => page.getByTestId('toast')
const cuenta = (page: Page, etapa: string): Locator => page.getByTestId(`etapa-${etapa}`).locator('span').last()

async function abrirPipeline(page: Page, b: string, query = ''): Promise<void> {
  await page.goto(`/recruiting/oportunidades/${b}/pipeline${query}`)
  await expect(page.getByTestId('pipeline-titulo')).toBeVisible()
  await expect(page.getByTestId('indicador-candidatos')).toBeVisible()
}

/** Contadores de la barra de etapas, «Total en proceso» y el contador del backend contra el modelo. */
async function verificarContadores(page: Page, clave: 'b1' | 'b2'): Promise<void> {
  const etapas = Object.values(modelo[clave]!)
  await expect(cuenta(page, 'Todas')).toHaveText(String(etapas.length))
  for (const e of ETAPAS) await expect(cuenta(page, e), `contador de ${e}`).toHaveText(String(etapas.filter((x) => x === e).length))
  const enProceso = etapas.filter((e) => e !== 'Descartados').length
  await expect(page.getByTestId('total-en-proceso')).toHaveText(String(enProceso))
  const contadores = await api.get<{ total: number }>(`/recruiting/oportunidades/${ids[clave]}/pipeline-contadores`)
  expect(contadores.total).toBe(enProceso)
}

/**
 * «Mover Etapa» por la interfaz: verifica la etapa actual del modal, que el destino esté entre las opciones permitidas,
 * el aviso, la fila, los contadores y lo guardado en el backend.
 */
async function mover(
  page: Page,
  clave: 'b1' | 'b2',
  c: Cand,
  destino: string,
  extra: { opciones?: string[]; comentario?: string; pretension?: string; archivo?: { name: string; mimeType: string; buffer: Buffer } } = {},
): Promise<void> {
  const actual = modelo[clave]![c.email]!
  await fila(page, c).getByTestId('mover-etapa').click()
  const modal = page.getByTestId('modal-mover')
  await expect(modal).toContainText(`Candidato: ${completo(c)}`)
  await expect(modal.getByText('Etapa actual:').locator('xpath=following-sibling::span[1]')).toHaveText(actual)
  if (extra.opciones) await expect(modal.getByTestId('nueva-etapa').locator('option')).toHaveText(extra.opciones)
  await modal.getByTestId('nueva-etapa').selectOption(destino)
  await expect(modal.locator('#pretensionSalarialInput')).toBeVisible({ visible: !!extra.pretension })
  if (extra.comentario) await modal.locator('#comentarioEtapa').fill(extra.comentario)
  if (extra.pretension) await modal.locator('#pretensionSalarialInput').pressSequentially(extra.pretension)
  if (extra.archivo) await modal.getByTestId('archivo-etapa').setInputFiles(extra.archivo)
  await modal.getByTestId('confirmar-avance').click()

  const adjunto = extra.archivo ? ' con archivo adjunto' : ''
  await expect(toast(page)).toHaveText(
    destino === 'Ingreso'
      ? `Se movió a ${completo(c)} a Ingreso${adjunto}. La búsqueda quedó Ganada y cerrada.`
      : `Se movió a ${completo(c)} a la etapa '${destino}'${adjunto}.`,
  )
  await expect(modal).toHaveCount(0)
  modelo[clave]![c.email] = destino
  const guardado = await enBackend(ids[clave], c)
  expect([guardado.etapa_actual, guardado.estado]).toEqual([destino, destino === 'Ingreso' ? 'Ingreso confirmado' : 'En proceso'])
  if (destino !== 'Ingreso') {
    await expect(fila(page, c).getByTestId('etapa-actual')).toHaveText(destino)
    await verificarContadores(page, clave)
  }
}

// ---- A. Búsquedas ------------------------------------------------------------------------------------------------

test.describe('A. alta de búsquedas desde la interfaz', () => {
  for (const [clave, titulo] of [
    ['b1', B1],
    ['b2', B2],
  ] as const) {
    test(`crea «${clave === 'b1' ? 'principal' : 'para el Ingreso'}», aparece en el listado, en su ficha y en Pipeline`, async ({ page, monitor }) => {
      await page.goto('/recruiting/oportunidades')
      await page.getByTestId('nueva-busqueda').click()
      await expect(page).toHaveURL(/\/v2\/recruiting\/oportunidades\/nueva$/)
      await expect(page.locator('#reclutador option')).not.toHaveCount(1)
      // Sin título: el navegador no deja enviar
      await page.getByTestId('guardar').click()
      await expect(page.locator('#titulo')).toHaveJSProperty('validity.valueMissing', true)
      expect(monitor.mutacionesDe(/POST .*\/oportunidades$/)).toHaveLength(0)

      await page.locator('#titulo').fill(titulo)
      await page.locator('#cliente').fill(CLIENTE)
      await page.locator('#vacantes').fill('2')
      await page.locator('#skills').fill(SKILL)
      await page.locator('#skills').press('Enter')
      await page.locator('#descripcion').fill('Busqueda del circuito E2E')
      const reclutador = await page.locator('#reclutador').inputValue()
      await page.getByTestId('guardar').click()
      await expect(page.getByText('Oportunidad creada exitosamente.')).toBeVisible()
      await expect(page).toHaveURL(/\/recruiting\/oportunidades/)

      // Persistencia
      const [creada] = await buscarBusqueda(titulo)
      expect(creada).toMatchObject({ titulo, cliente: CLIENTE, estado: 'Abierta', tipo: 'Efectiva', vacantes: 2, seniority: 'Senior', modalidad: 'Hibrido', recruiter_nombre: reclutador, skills: [SKILL], descripcion: 'Busqueda del circuito E2E' })
      ids[clave] = String(creada!.id)
      modelo[clave] = {}

      // Listado (filtro por texto) y ficha
      await page.goto(`/recruiting/oportunidades?busqueda=${encodeURIComponent(titulo)}`)
      const filaListado = page.getByTestId('fila-busqueda')
      await expect(filaListado).toHaveCount(1)
      await expect(filaListado.getByTestId('estado-busqueda')).toHaveText('Abierta')
      await filaListado.getByTestId('enlace-busqueda').click()
      await expect(page.getByTestId('busqueda-titulo')).toHaveText(titulo)
      await expect(page.getByTestId('asignados-vacio')).toBeVisible()

      // Vista global (fila con total 0) y selección individual (tarjeta)
      await page.goto('/recruiting/gestion-busquedas')
      const filaGlobal = page.locator('[data-testid="tabla-pipeline-global"] tbody tr', { hasText: titulo })
      await expect(filaGlobal).toContainText(CLIENTE)
      await expect(filaGlobal.locator('td').nth(1)).toHaveText('0')
      await page.locator('#pipeline-vista').selectOption({ label: 'Pipeline individual' })
      const tarjeta = page.getByTestId('tarjeta-busqueda').filter({ hasText: titulo })
      await expect(tarjeta).toContainText('2 vacantes')
      await expect(tarjeta).toContainText('Híbrido')
      await expect(tarjeta).toContainText('Abierta')
      await tarjeta.getByRole('link', { name: 'Gestionar Pipeline' }).click()
      await expect(page).toHaveURL(new RegExp(`/v2/recruiting/oportunidades/${ids[clave]}/pipeline$`))
      await expect(page.getByTestId('pipeline-titulo')).toHaveText(titulo)
      await expect(page.getByTestId('estado-busqueda')).toHaveText('Abierta')
      await expect(page.getByText('No hay candidatos asignados a esta búsqueda todavía')).toBeVisible()
      await expect(page.getByRole('link', { name: 'Agregar Candidato a esta Búsqueda' })).toBeVisible()
    })
  }
})

// ---- B. Candidatos ----------------------------------------------------------------------------------------------

test.describe('B. alta de candidatos desde la interfaz', () => {
  test('los obligatorios se validan antes de enviar', async ({ page, monitor }) => {
    await page.goto('/recruiting/candidatos/nuevo')
    await expect(page.getByTestId('guardar')).toBeVisible()
    await page.getByTestId('guardar').click()
    await expect(page.getByTestId('error-general')).toHaveText(
      'Por favor completá los campos obligatorios (*): Nombre, Apellido, Email y Teléfono.',
    )
    expect(monitor.mutacionesDe(/POST \/api\/v1\/recruiting\/candidatos/)).toHaveLength(0)
  })

  for (const clave of ['ana', 'bruno', 'carla', 'dora'] as const) {
    test(`alta de ${C[clave].nombre}: se guarda, aparece en la grilla y su ficha muestra lo cargado`, async ({ page }) => {
      const c = C[clave]
      await abrirGrilla(page)
      await page.getByTestId('nuevo-candidato').click()
      await expect(page).toHaveURL(/\/v2\/recruiting\/candidatos\/nuevo/)
      await page.locator('#nombre').fill(c.nombre)
      await page.locator('#apellido').fill(c.apellido)
      await page.locator('#email').fill(c.email)
      await page.locator('#telefono').fill('3515550101')
      await page.locator('#seniority').click()
      await page.getByRole('option', { name: 'Senior', exact: true }).click()
      for (const skill of ['Python', SKILL]) {
        await page.locator('#skills').fill(skill)
        await page.locator('#skills').press('Enter')
      }
      await page.getByTestId('guardar').click()
      await expect(page.getByText('Candidato guardado exitosamente.')).toBeVisible()
      await expect(page).toHaveURL(/\/v2\/recruiting\/candidatos$/, { timeout: 15_000 })

      // Grilla filtrada por email y ficha
      await abrirGrilla(page, `?busqueda=${encodeURIComponent(c.email)}`)
      await expect(page.locator(FILAS)).toHaveCount(1)
      await expect(page.locator(FILAS).first()).toContainText(completo(c))
      await page.locator(FILAS).first().getByTestId('accion-ver').click()
      await expect(page.getByTestId('detalle-nombre')).toHaveText(completo(c))
      const id = /\/candidatos\/([0-9a-f-]{36})/.exec(page.url())![1]!
      c.id = id
      const guardado = await api.get<Record<string, unknown>>(`/recruiting/candidatos/${id}`)
      expect(guardado).toMatchObject({ nombre: c.nombre, apellido: c.apellido, email: c.email, telefono: '3515550101', seniority: 'Senior', skills: ['Python', SKILL] })
      // Se recarga la ficha y los datos siguen ahí
      await page.reload()
      await expect(page.getByTestId('detalle-nombre')).toHaveText(completo(c))
    })
  }

  test('la grilla encuentra a los cuatro por texto', async ({ page }) => {
    await abrirGrilla(page, `?busqueda=${S}`)
    await expect(page.locator(FILAS)).toHaveCount(4)
  })
})

// ---- C. Incorporación a las búsquedas ---------------------------------------------------------------------------

test.describe('C. incorporación de candidatos a las búsquedas', () => {
  // Único dato preparado por API: un candidato cargado por otro usuario (admin), para probar el filtro «Propios».
  test.beforeAll(async () => {
    const otro = await api.post<{ id: string }>('/recruiting/candidatos', { nombre: OTRO.nombre, apellido: OTRO.apellido, email: OTRO.email, seniority: 'Senior', skills: ['Python'] })
    OTRO.id = otro.id
    await api.post(`/recruiting/oportunidades/${ids.b1}/candidatos`, { candidato_id: otro.id })
    modelo.b1![OTRO.email] = 'Candidato'
  })

  test('Ana, desde la grilla de Candidatos («Asignar a búsqueda»)', async ({ page }) => {
    await abrirGrilla(page, `?busqueda=${encodeURIComponent(C.ana.email)}`)
    await page.locator(FILAS).first().getByTestId('accion-asignar').click()
    const dialogo = page.getByRole('dialog')
    await expect(dialogo).toContainText(`Candidato: ${completo(C.ana)}`)
    const opcion = dialogo.getByTestId('busqueda-elegible').filter({ hasText: B1 })
    // La skill pedida y Senior en los dos: 70 % por skills + 30 % por seniority
    await expect(opcion).toContainText('100% match')
    await expect(opcion).toContainText(CLIENTE)
    await expect(dialogo.getByTestId('confirmar-asignacion')).toBeDisabled()
    await opcion.click()
    await dialogo.getByTestId('confirmar-asignacion').click()
    await expect(page.getByText('Candidato asignado a la búsqueda correctamente')).toBeVisible()
    modelo.b1![C.ana.email] = 'Candidato'
    expect((await enBackend(ids.b1, C.ana)).estado).toBe('En proceso')
  })

  test('Bruno, desde Smart Matching de la ficha de la búsqueda («Postular a Búsqueda»)', async ({ page }) => {
    await page.goto(`/recruiting/oportunidades/${ids.b1}`)
    const sugerido = page.getByTestId('tabla-sugeridos').locator('tr', { hasText: C.bruno.apellido })
    await expect(sugerido).toBeVisible()
    await expect(sugerido.getByTestId('porcentaje-match')).toHaveText('100%')
    await sugerido.getByTestId('postular').click()
    await expect(page.getByTestId('tabla-asignados').locator('tr', { hasText: C.bruno.apellido })).toHaveCount(1)
    modelo.b1![C.bruno.email] = 'Candidato'
    expect(await enBackend(ids.b1, C.bruno)).toBeTruthy()
  })

  test('Carla y Dora, desde el Pipeline vacío («Agregar Candidato a esta Búsqueda», pantalla Flask)', async ({ page }) => {
    for (const c of [C.carla, C.dora]) {
      await abrirPipeline(page, ids.b2)
      if (c === C.carla) {
        await page.getByRole('link', { name: 'Agregar Candidato a esta Búsqueda' }).click()
      } else {
        // Con candidatos ya no hay estado vacío: se entra por la misma URL que usa ese botón
        await page.goto(`/recruiting/oportunidades/${ids.b2}/agregar-candidato`)
      }
      await expect(page).toHaveURL(new RegExp(`/recruiting/oportunidades/${ids.b2}/agregar-candidato`))
      // Esta pantalla filtra sobre los 100 candidatos más recientes (su búsqueda al servidor nunca funcionó, ni en el
      // módulo original): los del circuito se crearon recién, así que están entre ellos.
      // Por email (único): «Ingreso…» también está contenido en «Reingreso…»
      await page.getByPlaceholder('Buscar candidato por nombre, apellido, email, dni o puesto...').fill(c.email)
      const filaAgregar = page.locator('tbody tr', { hasText: c.email })
      await expect(filaAgregar).toHaveCount(1)
      await filaAgregar.getByRole('button', { name: 'Asignar' }).click()
      await expect(page.getByText(`${c.nombre} ${c.apellido} fue asignado a la búsqueda exitosamente.`)).toBeVisible()
      await expect(page).toHaveURL(new RegExp(`/v2/recruiting/oportunidades/${ids.b2}$`), { timeout: 15_000 })
      modelo.b2![c.email] = 'Candidato'
    }
  })

  test('el Pipeline de cada búsqueda muestra a sus candidatos en Candidato, con sus datos y contadores', async ({ page }) => {
    await abrirPipeline(page, ids.b1)
    await expect(page.getByTestId('indicador-candidatos')).toHaveText(/Mostrando 3 de 3 candidatos/)
    for (const c of [C.ana, C.bruno]) {
      const f = fila(page, c)
      await expect(f.getByTestId('etapa-actual')).toHaveText('Candidato')
      await expect(f).toContainText(c.email)
      await expect(f).toContainText('Senior')
      await expect(f).toContainText('3515550101')
      await expect(f).toContainText('Interno')
      await expect(f.getByTestId('mover-etapa')).toBeEnabled()
    }
    await verificarContadores(page, 'b1')
    // «Propios»: el candidato que cargó otro usuario no se ve
    await page.locator('#filtro-origen-candidato').selectOption({ label: 'Propios' })
    await expect(page).toHaveURL(/alcance_candidatos=propios/)
    await expect(page.getByTestId('indicador-candidatos')).toHaveText(/Mostrando 2 de 2 candidatos/)
    await expect(page.getByTestId('fila-candidato').filter({ hasText: OTRO.apellido })).toHaveCount(0)

    await abrirPipeline(page, ids.b2)
    await expect(page.getByTestId('indicador-candidatos')).toHaveText(/Mostrando 2 de 2 candidatos/)
    await verificarContadores(page, 'b2')
  })
})

// ---- D/E/F. Recorrido del embudo ----------------------------------------------------------------------------------

test.describe('D. recorrido del embudo (Ana: secuencial con salto Validación → Oferta y adjunto)', () => {
  test('Candidato → Screening → Entrevista RRHH, con nota', async ({ page }) => {
    await abrirPipeline(page, ids.b1)
    await mover(page, 'b1', C.ana, 'Screening', { opciones: ['Screening'], comentario: 'Primer contacto ok' })
    expect((await enBackend(ids.b1, C.ana)).feedback_etapa).toBe('Primer contacto ok')
    await mover(page, 'b1', C.ana, 'Entrevista RRHH', { opciones: ['Entrevista RRHH'] })
  })

  test('E. Entrevista RRHH → Líder: la pretensión es obligatoria, se valida, se formatea y se guarda', async ({ page, monitor }) => {
    await abrirPipeline(page, ids.b1)
    await fila(page, C.ana).getByTestId('mover-etapa').click()
    const modal = page.getByTestId('modal-mover')
    await expect(modal.getByTestId('nueva-etapa')).toHaveValue('Entrevista Líder Dicsys')
    const pretension = modal.locator('#pretensionSalarialInput')
    await expect(pretension).toBeVisible()
    // Sin completar: no viaja nada
    await modal.getByTestId('confirmar-avance').click()
    await expect(modal.getByTestId('error-pretension')).toHaveText('La pretensión salarial es obligatoria.')
    // Letras: se descartan al escribir (queda vacío)
    await pretension.pressSequentially('abc')
    await expect(pretension).toHaveValue('')
    // Cero: no es un importe válido
    await pretension.pressSequentially('0')
    await expect(pretension).toHaveValue('$ 0')
    await modal.getByTestId('confirmar-avance').click()
    await expect(modal.getByTestId('error-pretension')).toHaveText('La pretensión salarial debe ser un importe mayor a cero.')
    expect(monitor.mutacionesDe(/\/etapa$/)).toHaveLength(0)
    await page.keyboard.press('Escape')

    await mover(page, 'b1', C.ana, 'Entrevista Líder Dicsys', {
      opciones: ['Entrevista Líder Dicsys'],
      pretension: '1850000',
    })
    expect((await enBackend(ids.b1, C.ana)).pretension_salarial_bruta_ars).toBe(1850000)
    const cuerpo = JSON.parse(monitor.mutacionesDe(/PUT .*\/etapa$/)[0]!.cuerpo!)
    expect(cuerpo).toMatchObject({ etapa_actual: 'Entrevista Líder Dicsys', estado: 'En proceso', pretension_salarial_bruta_ars: 1850000 })
  })

  test('Líder → Validación Administración → (salto) Oferta', async ({ page }) => {
    await abrirPipeline(page, ids.b1)
    await mover(page, 'b1', C.ana, 'Validación Administración', { opciones: ['Validación Administración', 'Entrevista Cliente'] })
    await abrirPipeline(page, ids.b1) // recarga: el estado persiste
    await expect(fila(page, C.ana).getByTestId('etapa-actual')).toHaveText('Validación Administración')
  })

  test('F. Validación → Oferta con adjunto: formatos y tamaño, envío multipart y archivo asociado al movimiento', async ({ page }) => {
    await abrirPipeline(page, ids.b1)
    await fila(page, C.ana).getByTestId('mover-etapa').click()
    const modal = page.getByTestId('modal-mover')
    await expect(modal.getByTestId('nueva-etapa').locator('option')).toHaveText(['Entrevista Cliente', 'Oferta'])
    await expect(modal.getByTestId('archivo-etapa')).toHaveAttribute('accept', '.pdf,.doc,.docx,.png,.jpg,.jpeg,.xlsx,.xls,.txt,.zip,.rar')
    // Formato no admitido y más de 10 MB: se descartan, como en la pantalla anterior
    await modal.getByTestId('archivo-etapa').setInputFiles({ name: 'virus.exe', mimeType: 'application/octet-stream', buffer: Buffer.from('x') })
    await expect(modal.getByTestId('archivo-elegido')).toHaveCount(0)
    await modal.getByTestId('archivo-etapa').setInputFiles({ name: 'grande.pdf', mimeType: 'application/pdf', buffer: Buffer.alloc(10 * 1024 * 1024 + 1) })
    await expect(modal.getByTestId('archivo-elegido')).toHaveCount(0)
    await page.keyboard.press('Escape')

    const pedido = page.waitForRequest((r) => r.method() === 'POST' && /\/recruiting\/oportunidades\/.+\/etapa$/.test(r.url()))
    await mover(page, 'b1', C.ana, 'Oferta', {
      archivo: { name: `oferta-${S}.pdf`, mimeType: 'application/pdf', buffer: crearPdf(['Oferta firmada E2E']) },
    })
    expect((await pedido).headers()['content-type']).toMatch(/^multipart\/form-data/)
    const archivos = await api.get<{ nombre_archivo: string; etapa_id: string; tamano: number }[]>(
      `/recruiting/oportunidades/${ids.b1}/candidatos/${C.ana.id}/archivos-etapa`,
    )
    expect(archivos.map((a) => [a.nombre_archivo, a.etapa_id])).toEqual([[`oferta-${S}.pdf`, 'Oferta']])
  })

  test('«Ver Detalles» (pantalla Flask) muestra el historial, la pretensión y el adjunto descargable; «Volver» regresa', async ({ page }) => {
    await abrirPipeline(page, ids.b1)
    await fila(page, C.ana).getByRole('link', { name: 'Ver Detalles' }).click()
    await expect(page).toHaveURL(new RegExp(`/recruiting/oportunidades/${ids.b1}/candidatos/${C.ana.id}/detalle\\?origen=pipeline`))
    await expect(page.getByText('Pretensión salarial bruta: $ 1.850.000')).toBeVisible()
    await expect(page.getByText('"Primer contacto ok"')).toBeVisible()
    await expect(page.getByText(`oferta-${S}.pdf`).first()).toBeVisible()
    const descarga = page.locator('a[href*="/archivos-etapa/"]').first()
    const r = await page.request.get((await descarga.getAttribute('href'))!)
    expect(r.status()).toBe(200)
    expect((await r.body()).subarray(0, 4).toString()).toBe('%PDF')
    await page.getByText('Volver al pipeline').click()
    await expect(page).toHaveURL(new RegExp(`/v2/recruiting/oportunidades/${ids.b1}/pipeline`))
  })
})

test.describe('G/H. descarte y reingreso (Bruno), y saltos Líder → Cliente → Examen', () => {
  test('Candidato → Screening', async ({ page }) => {
    await abrirPipeline(page, ids.b1)
    await mover(page, 'b1', C.bruno, 'Screening')
  })

  test('G. Descartar: motivos de la etapa, observaciones, filtro Descartados y persistencia', async ({ page }) => {
    const motivosEtapa = (await api.get<{ motivo: string }[]>('/recruiting/motivos-descarte?etapa=Screening')).map((m) => m.motivo)
    await abrirPipeline(page, ids.b1)
    await fila(page, C.bruno).getByTestId('descartar').click()
    const modal = page.getByTestId('modal-descartar')
    await expect(modal).toContainText(`Candidato: ${completo(C.bruno)}`)
    await expect(modal).toContainText('Etapa activa de descarte: Screening')
    await expect(modal.getByTestId('motivo-descarte').locator('option')).toHaveText(motivosEtapa)
    await expect(modal.getByTestId('motivo-descarte')).toHaveValue(motivosEtapa[0]!)
    const motivo = motivosEtapa[motivosEtapa.length - 1]!
    await modal.getByTestId('motivo-descarte').selectOption(motivo)
    await modal.locator('#comentarioDescarte').fill('No se presento a la entrevista')
    await modal.getByTestId('confirmar-descarte').click()

    await expect(toast(page)).toHaveText(`El candidato ${completo(C.bruno)} fue marcado como descartado.`)
    modelo.b1![C.bruno.email] = 'Descartados'
    await expect(fila(page, C.bruno).getByTestId('etapa-actual')).toHaveText('Descartados')
    await expect(fila(page, C.bruno)).toContainText(`Motivo: ${motivo}`)
    await expect(fila(page, C.bruno).getByTestId('mover-etapa')).toHaveCount(0)
    await verificarContadores(page, 'b1')
    await page.getByTestId('etapa-Descartados').click()
    await expect(page.getByTestId('fila-candidato')).toHaveCount(1)
    await expect(fila(page, C.bruno).getByTestId('reingresar')).toBeVisible()
    const guardado = await enBackend(ids.b1, C.bruno)
    expect([guardado.etapa_actual, guardado.estado, guardado.motivo_descarte, guardado.feedback_etapa]).toEqual([
      'Descartados',
      'Descartado',
      motivo,
      'No se presento a la entrevista',
    ])
  })

  test('H. Reingresar: motivo obligatorio, vuelve a Entrevista RRHH y queda en el historial', async ({ page }) => {
    await abrirPipeline(page, ids.b1)
    await fila(page, C.bruno).getByTestId('reingresar').click()
    const modal = page.getByTestId('modal-reingresar')
    await expect(modal.locator('#etapaReingreso')).toHaveValue('Entrevista RRHH')
    await expect(modal.getByTestId('confirmar-reingreso')).toBeDisabled()
    await modal.getByTestId('motivo-reingreso').fill('   ')
    await expect(modal.getByTestId('confirmar-reingreso')).toBeDisabled()
    await modal.getByTestId('motivo-reingreso').fill('Se flexibilizo el perfil')
    await modal.getByTestId('confirmar-reingreso').click()

    await expect(toast(page)).toHaveText(`El candidato ${completo(C.bruno)} reingresó exitosamente al proceso en 'Entrevista RRHH'.`)
    modelo.b1![C.bruno.email] = 'Entrevista RRHH'
    await expect(fila(page, C.bruno).getByTestId('etapa-actual')).toHaveText('Entrevista RRHH')
    await expect(fila(page, C.bruno)).not.toContainText('Motivo:')
    await verificarContadores(page, 'b1')
    const guardado = await enBackend(ids.b1, C.bruno)
    expect([guardado.etapa_actual, guardado.estado, guardado.motivo_descarte, guardado.feedback_etapa]).toEqual([
      'Entrevista RRHH',
      'En proceso',
      null,
      'Se flexibilizo el perfil',
    ])
    const historial = await api.get<{ etapa_nueva: string; descripcion: string | null; motivo_descarte: string | null }[]>(
      `/recruiting/oportunidades/${ids.b1}/candidatos/${C.bruno.id}/historial`,
    )
    // La asignación no es un movimiento: el historial tiene exactamente los tres cambios hechos en la interfaz
    expect(historial.map((h) => h.etapa_nueva)).toEqual(['Screening', 'Descartados', 'Entrevista RRHH'])
    expect(historial[1]!.motivo_descarte).toBeTruthy()
    expect(historial[1]!.descripcion).toBe('No se presento a la entrevista')
    expect(historial[2]!.descripcion).toBe('Reingreso al proceso: Se flexibilizo el perfil')
  })

  test('RRHH → Líder → (salto) Entrevista Cliente → (salto) Examen Médico Preocupacional', async ({ page }) => {
    await abrirPipeline(page, ids.b1)
    await mover(page, 'b1', C.bruno, 'Entrevista Líder Dicsys', { pretension: '2000000' })
    await mover(page, 'b1', C.bruno, 'Entrevista Cliente', { opciones: ['Validación Administración', 'Entrevista Cliente'] })
    await mover(page, 'b1', C.bruno, 'Examen Médico Preocupacional', { opciones: ['Oferta', 'Examen Médico Preocupacional'] })
    expect((await enBackend(ids.b1, C.bruno)).pretension_salarial_bruta_ars).toBe(2000000)
  })

  test('vista global: cifras por columna iguales al backend, detalle emergente y «Propios»', async ({ page }) => {
    const resumen = await api.get<{ columnas: { clave: string; nombre: string; etapas: string[] }[] }>(
      '/recruiting/pipeline-resumen?estado=Abierta',
    )
    await page.goto('/recruiting/gestion-busquedas')
    await page.getByTestId('buscar-busqueda').fill(B1)
    const filaGlobal = page.locator('[data-testid="tabla-pipeline-global"] tbody tr', { hasText: B1 })
    await expect(page.locator('[data-testid="tabla-pipeline-global"] tbody tr')).toHaveCount(1)
    const etapas = Object.values(modelo.b1!)
    await expect(filaGlobal.locator('td').nth(1)).toHaveText(String(etapas.filter((e) => e !== 'Descartados').length))
    for (const [i, col] of resumen.columnas.entries()) {
      const n = etapas.filter((e) => col.etapas.includes(e)).length
      await expect(filaGlobal.locator('td').nth(2 + i), `columna ${col.nombre}`).toHaveText(n ? String(n) : '–')
    }
    // Detalle emergente de la columna Oferta (Ana en Oferta y Bruno en Examen Médico)
    const indice = resumen.columnas.findIndex((c) => c.etapas.includes('Oferta'))
    await filaGlobal.locator('td').nth(2 + indice).getByTestId('cifra-columna').hover()
    const popup = page.getByTestId('popup-columna')
    await expect(popup).toContainText(`Candidatos en ${resumen.columnas[indice]!.nombre} (${B1})`)
    await expect(popup).toContainText(`Nombre: ${completo(C.ana)}`)
    await expect(popup).toContainText('Pretensión: 1.850.000 ARS')
    await expect(popup).toContainText(`Nombre: ${completo(C.bruno)}`)
    await expect(popup).toContainText('Pretensión: 2.000.000 ARS')
    await page.mouse.move(2, 2)
    // «Propios»: el candidato del otro usuario (en Candidato) deja de contar
    await page.locator('#filtro-origen-candidato').selectOption({ label: 'Propios' })
    await expect(page).toHaveURL(/alcance_candidatos=propios/)
    await page.getByTestId('buscar-busqueda').fill(B1)
    await expect(filaGlobal.locator('td').nth(1)).toHaveText(String(etapas.filter((e) => e !== 'Descartados').length - 1))
  })
})

// ---- I. Ingreso ---------------------------------------------------------------------------------------------------

test.describe('I. proceso completo hasta Ingreso (Carla) en una búsqueda aparte', () => {
  test('error real del backend: otro usuario ya movió a Dora; el aviso muestra el rechazo y nada cambia', async ({ page, monitor }) => {
    monitor.permitir(/^400 PUT \/recruiting\/oportunidades\/.+\/etapa$/)
    await abrirPipeline(page, ids.b2)
    await fila(page, C.dora).getByTestId('mover-etapa').click()
    // Mientras el modal está abierto, otro usuario la mueve a Screening
    await api.put(`/recruiting/oportunidades/${ids.b2}/candidatos/${C.dora.id}/etapa`, { etapa_actual: 'Screening', estado: 'En proceso' })
    await page.getByTestId('modal-mover').getByTestId('confirmar-avance').click()
    await expect(toast(page)).toContainText('Transición de etapa inválida')
    await expect(page.getByTestId('modal-mover')).toHaveCount(0)
    expect((await enBackend(ids.b2, C.dora)).etapa_actual).toBe('Screening')
    modelo.b2![C.dora.email] = 'Screening'
    await abrirPipeline(page, ids.b2)
    await expect(fila(page, C.dora).getByTestId('etapa-actual')).toHaveText('Screening')
  })

  test('las ocho etapas del embudo en orden, de Candidato a Examen Médico Preocupacional', async ({ page }) => {
    await abrirPipeline(page, ids.b2)
    await mover(page, 'b2', C.carla, 'Screening')
    await mover(page, 'b2', C.carla, 'Entrevista RRHH')
    await mover(page, 'b2', C.carla, 'Entrevista Líder Dicsys', { pretension: '1500000' })
    await mover(page, 'b2', C.carla, 'Validación Administración')
    await mover(page, 'b2', C.carla, 'Entrevista Cliente', { opciones: ['Entrevista Cliente', 'Oferta'] })
    await mover(page, 'b2', C.carla, 'Oferta', { opciones: ['Oferta', 'Examen Médico Preocupacional'] })
    await mover(page, 'b2', C.carla, 'Examen Médico Preocupacional', { opciones: ['Examen Médico Preocupacional'] })
    const historial = await api.get<{ etapa_nueva: string }[]>(`/recruiting/oportunidades/${ids.b2}/candidatos/${C.carla.id}/historial`)
    expect(historial.map((h) => h.etapa_nueva)).toEqual(ETAPAS.slice(1, 8))
  })

  test('Examen → Ingreso (con adjunto): Ingreso Confirmado, búsqueda Ganada y cerrada, sin más movimientos', async ({ page }) => {
    await abrirPipeline(page, ids.b2)
    const recarga = page.waitForEvent('load', { timeout: 15_000 })
    await mover(page, 'b2', C.carla, 'Ingreso', {
      opciones: ['Ingreso'],
      archivo: { name: `alta-${S}.pdf`, mimeType: 'application/pdf', buffer: crearPdf(['Alta E2E']) },
    })
    await recarga
    await expect(page.getByTestId('pipeline-titulo')).toBeVisible()
    await expect(page.getByTestId('aviso-busqueda-ganada')).toBeVisible()
    await expect(page.getByTestId('estado-busqueda')).toHaveText('Ganada')
    await expect(fila(page, C.carla).getByTestId('etapa-actual')).toHaveText('Ingreso')
    await expect(fila(page, C.carla)).toContainText('Ingreso Confirmado')
    await expect(fila(page, C.carla).getByTestId('mover-etapa')).toHaveCount(0)
    const moverDora = fila(page, C.dora).getByTestId('mover-etapa')
    await expect(moverDora).toBeDisabled()
    await expect(moverDora).toHaveAttribute('title', 'La búsqueda está Ganada y cerrada')
    await expect(fila(page, C.dora).getByTestId('descartar')).toBeDisabled()
    await verificarContadores(page, 'b2')

    // Backend: Ganada, Carla con Ingreso confirmado y el adjunto del Ingreso guardado
    expect((await api.get<{ estado: string }>(`/recruiting/oportunidades/${ids.b2}`)).estado).toBe('Ganada')
    const archivos = await api.get<{ nombre_archivo: string; etapa_id: string }[]>(
      `/recruiting/oportunidades/${ids.b2}/candidatos/${C.carla.id}/archivos-etapa`,
    )
    expect(archivos.map((a) => [a.nombre_archivo, a.etapa_id])).toEqual([[`alta-${S}.pdf`, 'Ingreso']])
    // El backend también rechaza cualquier movimiento posterior (409)
    const r = await api.pedir('PUT', `/recruiting/oportunidades/${ids.b2}/candidatos/${C.dora.id}/etapa`, { etapa_actual: 'Entrevista RRHH', estado: 'En proceso' }, [409])
    expect(r.estado).toBe(409)
    expect((await enBackend(ids.b2, C.dora)).etapa_actual).toBe('Screening')
  })

  test('la búsqueda Ganada sale de la vista global y de la selección individual, y su ficha queda de solo consulta', async ({ page }) => {
    await page.goto('/recruiting/gestion-busquedas')
    await expect(page.getByTestId('tabla-pipeline-global')).toBeVisible()
    await expect(page.locator('[data-testid="tabla-pipeline-global"] tbody tr', { hasText: B2 })).toHaveCount(0)
    await page.goto('/recruiting/gestion-busquedas?vista=individual')
    await expect(page.getByTestId('tarjeta-busqueda').first()).toBeVisible()
    await expect(page.getByTestId('tarjeta-busqueda').filter({ hasText: B2 })).toHaveCount(0)
    await page.goto(`/recruiting/oportunidades/${ids.b2}`)
    await expect(page.getByTestId('aviso-busqueda-ganada')).toBeVisible()
    // «Agregar candidato» de una Ganada vuelve a la ficha con el aviso (Flask, como antes)
    await page.goto(`/recruiting/oportunidades/${ids.b2}/agregar-candidato`)
    await expect(page).toHaveURL(new RegExp(`/v2/recruiting/oportunidades/${ids.b2}$`))
  })
})

// ---- Navegación, sesión y estados -------------------------------------------------------------------------------

test.describe('navegación, sesión y estados vacíos', () => {
  test('menú: Candidatos → Búsquedas → Pipeline, y la ficha del candidato vuelve al Pipeline', async ({ page }) => {
    await page.goto('/recruiting/candidatos')
    await page.locator('aside a', { hasText: /^\s*Búsquedas\s*$/ }).first().click()
    await expect(page).toHaveURL(/\/v2\/recruiting\/oportunidades/)
    await page.locator('aside a', { hasText: /^\s*Pipeline\s*$/ }).first().click()
    await expect(page).toHaveURL(/\/v2\/recruiting\/gestion-busquedas$/)
    await expect(page.locator('aside a', { hasText: /^\s*Pipeline\s*$/ }).first()).toHaveAttribute('aria-current', 'page')

    await abrirPipeline(page, ids.b1, '?alcance_candidatos=propios')
    await fila(page, C.ana).getByRole('link', { name: completo(C.ana) }).click()
    await expect(page.getByTestId('detalle-nombre')).toHaveText(completo(C.ana))
    await page.getByTestId('volver').click()
    await expect(page).toHaveURL(new RegExp(`/v2/recruiting/oportunidades/${ids.b1}/pipeline\\?alcance_candidatos=propios$`))
    await expect(fila(page, C.ana).getByTestId('etapa-actual')).toHaveText('Oferta')
    // «Ver ficha de búsqueda» y su «Volver» regresan al Pipeline
    await page.getByTestId('ver-ficha').click()
    await expect(page.getByTestId('busqueda-titulo')).toHaveText(B1)
    await page.getByTestId('volver').click()
    await expect(page).toHaveURL(new RegExp(`/v2/recruiting/oportunidades/${ids.b1}/pipeline`))
  })

  test('sesión vencida (401 de la API): vuelve al login', async ({ page, monitor }) => {
    monitor.permitir(/401/)
    await page.route('**/api/v1/recruiting/oportunidades/*/pipeline-candidatos*', (r) =>
      r.fulfill({ status: 401, contentType: 'application/json', body: JSON.stringify({ detail: 'Tu sesión venció' }) }),
    )
    await page.goto(`/recruiting/oportunidades/${ids.b1}/pipeline`)
    await expect(page).toHaveURL(/\/login/)
  })

  test('sin búsquedas abiertas: estados vacíos de la vista global y de la selección individual', async ({ page }) => {
    await page.route('**/api/v1/recruiting/pipeline-resumen*', (r) =>
      r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ columnas: [], items: [] }) }),
    )
    await page.route('**/api/v1/recruiting/oportunidades?*', (r) =>
      r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: [], total: 0, pagina: 1, por_pagina: 100, total_paginas: 1 }) }),
    )
    await page.goto('/recruiting/gestion-busquedas')
    await expect(page.getByTestId('pipeline-global-vacio')).toContainText('No hay búsquedas para mostrar')
    await expect(page.getByRole('link', { name: 'Crear nueva búsqueda' })).toHaveAttribute('href', /^\/recruiting\/oportunidades\/nueva\?volver=/)
    await page.locator('#pipeline-vista').selectOption({ label: 'Pipeline individual' })
    await expect(page.getByTestId('pipeline-individual-vacio')).toContainText('No hay búsquedas abiertas')
  })

  test('error del backend al cargar la vista global: se muestra su mensaje', async ({ page, monitor }) => {
    monitor.permitir(/^500 GET \/api\/v1\/recruiting\/pipeline-resumen/)
    await page.route('**/api/v1/recruiting/pipeline-resumen*', (r) =>
      r.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ detail: 'Falla simulada del backend' }) }),
    )
    await page.goto('/recruiting/gestion-busquedas')
    await expect(page.getByTestId('pipeline-error')).toHaveText('Falla simulada del backend')
  })

  test('acceso sin el ítem Pipeline (grupo EXTERNOS): 403 en la URL de siempre y en /v2', async ({ browser }) => {
    const contexto = await browser.newContext({ storageState: estadoDe('externo') })
    const pagina = await contexto.newPage()
    for (const ruta of [`/recruiting/oportunidades/${ids.b1}/pipeline`, `/v2/recruiting/oportunidades/${ids.b1}/pipeline`, '/recruiting/asignar-candidato']) {
      const r = await pagina.goto(ruta)
      expect(r?.status(), ruta).toBe(403)
    }
    await contexto.close()
  })
})
