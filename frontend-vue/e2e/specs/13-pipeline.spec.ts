import type { Page } from '@playwright/test'

import { ADMIN, ClienteApi } from '../api'
import { crearPdf } from '../archivos'
import { estadoDe, expect, test } from '../fixtures'

/**
 * Pipeline (ítem «gestion_busquedas»). Criterio legacy (asignar_candidato_hub.html y pipeline.html): vista global con
 * búsqueda por texto y detalle emergente de cada cifra, selección individual, filtro de candidatos y selector de vista
 * en la URL; Pipeline de una búsqueda con contadores y filtro por etapa, Mover Etapa (saltos, pretensión salarial de
 * RRHH a Líder y adjunto), Descartar (motivos de la etapa), Reingresar, Ingreso que cierra la búsqueda como Ganada,
 * enlaces con «volver» y acceso con el ítem (sin él: 403). Los datos se crean con el backend dentro de la prueba y el
 * resultado se comprueba también contra el backend.
 */
const SUFIJO = Date.now().toString(36)
const CLIENTE = 'Cliente Pipeline E2E'
const TITULO = `Pipeline Vue E2E ${SUFIJO}`
const TITULO_GANABLE = `Pipeline Ganable E2E ${SUFIJO}`

interface Creado {
  id: string
}
interface Fila {
  candidato_id: string
  etapa_actual: string
  estado: string
  feedback_etapa: string | null
  motivo_descarte: string | null
  pretension_salarial_bruta_ars: number | null
}

let api: ClienteApi
let busqueda: Creado
let ganable: Creado
const cands: Record<string, { id: string; nombre: string }> = {}

const etapa = (op: string, cand: string, cuerpo: Record<string, unknown>) =>
  api.put(`/recruiting/oportunidades/${op}/candidatos/${cand}/etapa`, cuerpo)
const filaEnBackend = async (op: string, clave: string): Promise<Fila> => {
  const filas = await api.get<Fila[]>(`/recruiting/oportunidades/${op}/pipeline-candidatos`)
  return filas.find((f) => f.candidato_id === cands[clave]!.id)!
}

test.beforeAll(async () => {
  api = await ClienteApi.ingresar(ADMIN.email, ADMIN.password)
  const alta = (titulo: string) =>
    api.post<Creado>('/recruiting/oportunidades', {
      cliente: CLIENTE,
      titulo,
      estado: 'Abierta',
      seniority: 'Semi Senior',
      modalidad: 'Hibrido',
      vacantes: 2,
      skills: [],
      habilidades: [],
      skills_deseadas: [],
    })
  busqueda = await alta(TITULO)
  ganable = await alta(TITULO_GANABLE)

  const candidato = async (clave: string, nombre: string) => {
    const apellido = `${nombre}${SUFIJO}`
    const c = await api.post<{ id: string }>('/recruiting/candidatos', {
      nombre: 'Pipe',
      apellido,
      email: `pipe.${clave}.${SUFIJO}@example.com`,
      telefono: '+5493515550199',
      seniority: 'Senior',
    })
    cands[clave] = { id: c.id, nombre: `Pipe ${apellido}` }
  }
  for (const [clave, nombre] of [
    ['avanza', 'Avanza'],
    ['rrhh', 'Rrhh'],
    ['adjunto', 'Adjunto'],
    ['descartado', 'Descartado'],
    ['examen', 'Examen'],
    ['activoGanada', 'Activo'],
    ['descartadoGanada', 'Fuera'],
  ] as const) {
    await candidato(clave, nombre)
  }

  // Búsqueda principal: uno en Candidato (asignado), uno en Entrevista RRHH, uno en Oferta y uno descartado.
  await api.post(`/recruiting/oportunidades/${busqueda.id}/candidatos`, { candidato_id: cands.avanza!.id })
  await etapa(busqueda.id, cands.rrhh!.id, { etapa_actual: 'Entrevista RRHH', estado: 'En proceso' })
  await etapa(busqueda.id, cands.adjunto!.id, { etapa_actual: 'Oferta', estado: 'En proceso' })
  await etapa(busqueda.id, cands.descartado!.id, { etapa_actual: 'Screening', estado: 'En proceso' })
  const [motivo] = await api.get<{ motivo: string }[]>('/recruiting/motivos-descarte?etapa=Screening')
  await etapa(busqueda.id, cands.descartado!.id, { etapa_actual: 'Descartados', estado: 'Descartado', motivo_descarte: motivo!.motivo })

  // Búsqueda que se gana: uno en Examen Médico (pasa a Ingreso), uno activo y uno descartado.
  await etapa(ganable.id, cands.examen!.id, { etapa_actual: 'Examen Médico Preocupacional', estado: 'En proceso' })
  await api.post(`/recruiting/oportunidades/${ganable.id}/candidatos`, { candidato_id: cands.activoGanada!.id })
  await etapa(ganable.id, cands.descartadoGanada!.id, { etapa_actual: 'Screening', estado: 'En proceso' })
  await etapa(ganable.id, cands.descartadoGanada!.id, { etapa_actual: 'Descartados', estado: 'Descartado', motivo_descarte: motivo!.motivo })
})

const fila = (page: Page, clave: string) => page.getByTestId('fila-candidato').filter({ hasText: cands[clave]!.nombre })
async function abrirPipeline(page: Page, id: string, query = ''): Promise<void> {
  await page.goto(`/recruiting/oportunidades/${id}/pipeline${query}`)
  await expect(page.getByTestId('pipeline-titulo')).toBeVisible()
}
const toast = (page: Page) => page.getByTestId('toast')
const itemMenu = (page: Page, nombre: string) => page.locator('aside a', { hasText: new RegExp(`^\\s*${nombre}\\s*$`) }).first()

test.describe('acceso', () => {
  test.use({ storageState: estadoDe('autorizado') })

  test('la URL del menú abre la vista global en Vue y resalta «Pipeline»', async ({ page }) => {
    await page.goto('/recruiting/gestion-busquedas')
    await expect(page).toHaveURL(/\/v2\/recruiting\/gestion-busquedas$/)
    await expect(page.getByRole('heading', { level: 1, name: 'Pipeline' })).toBeVisible()
    await expect(page.getByTestId('tabla-pipeline-global')).toBeVisible()
    await expect(itemMenu(page, 'Pipeline')).toHaveAttribute('aria-current', 'page')
    await expect(page).toHaveTitle('Pipeline - Recruiting - Dicsys Core')
  })

  test('el Pipeline de una búsqueda conserva sus parámetros, arranca en «Todas» y resalta «Pipeline»', async ({ page }) => {
    await page.goto(`/recruiting/oportunidades/${busqueda.id}/pipeline?etapas=Oferta&columna=Oferta`)
    await expect(page).toHaveURL(new RegExp(`/v2/recruiting/oportunidades/${busqueda.id}/pipeline\\?etapas=Oferta&columna=Oferta$`))
    await expect(page.getByTestId('pipeline-titulo')).toHaveText(TITULO)
    await expect(page.getByTestId('etapa-Todas')).toHaveClass(/bg-slate-800/)
    await expect(page.getByTestId('fila-candidato')).toHaveCount(4)
    await expect(itemMenu(page, 'Pipeline')).toHaveAttribute('aria-current', 'page')
    await expect(itemMenu(page, 'Búsquedas')).not.toHaveAttribute('aria-current', 'page')
    await expect(page).toHaveTitle(`Pipeline — ${TITULO} | Recruiting | Dicsys Core`)
  })

  test('acceso directo a /v2 con el permiso: abre', async ({ page }) => {
    const r = await page.goto(`/v2/recruiting/oportunidades/${busqueda.id}/pipeline`)
    expect(r?.status()).toBe(200)
    await expect(page.getByTestId('pipeline-titulo')).toBeVisible()
  })

  test('una búsqueda inexistente vuelve a Pipeline con el aviso', async ({ page, monitor }) => {
    monitor.permitir(/^404 GET \/api\/v1\/recruiting\/oportunidades\//)
    await page.goto('/recruiting/oportunidades/00000000-0000-4000-8000-000000000000/pipeline')
    await expect(page).toHaveURL(/\/v2\/recruiting\/gestion-busquedas$/)
    await expect(page.getByText('La búsqueda solicitada no existe o no fue encontrada.')).toBeVisible()
  })
})

test.describe('sin el ítem Pipeline', () => {
  test.use({ storageState: estadoDe('sinPermiso') })

  for (const ruta of ['/recruiting/gestion-busquedas', '/v2/recruiting/gestion-busquedas', '/recruiting/oportunidades/ID/pipeline', '/v2/recruiting/oportunidades/ID/pipeline']) {
    test(`${ruta} responde 403`, async ({ page, monitor }) => {
      monitor.permitir(/^403 GET \/(recruiting|v2)\//)
      const r = await page.goto(ruta.replace('ID', busqueda.id))
      expect(r?.status()).toBe(403)
    })
  }
})

test.describe('vista global y selección individual', () => {
  test.use({ storageState: estadoDe('autorizado') })

  test('búsqueda por texto, «Limpiar búsqueda» y detalle emergente de una cifra', async ({ page }) => {
    await page.goto('/recruiting/gestion-busquedas')
    const filaGlobal = page.locator('[data-testid="tabla-pipeline-global"] tbody tr', { hasText: TITULO })
    await expect(filaGlobal).toBeVisible()
    await expect(filaGlobal).toContainText(`${CLIENTE}`)
    await expect(filaGlobal).toContainText('Interna')

    await page.getByTestId('buscar-busqueda').fill('zzz-no-existe')
    await expect(page.getByText('No se encontraron búsquedas')).toBeVisible()
    await page.getByRole('button', { name: 'Limpiar búsqueda' }).click()
    await expect(filaGlobal).toBeVisible()
    await page.getByTestId('buscar-busqueda').fill(SUFIJO)
    await expect(page.locator('[data-testid="tabla-pipeline-global"] tbody tr')).toHaveCount(2)

    const cifra = filaGlobal.getByTestId('cifra-columna').first()
    await cifra.hover()
    const popup = page.getByTestId('popup-columna')
    await expect(popup).toBeVisible()
    await expect(popup).toContainText(`(${TITULO})`)
    await expect(popup.getByText('Nombre:').first()).toBeVisible()
    await page.mouse.move(5, 5)
    await expect(popup).toBeHidden()

    await cifra.click()
    await expect(page).toHaveURL(new RegExp(`/v2/recruiting/oportunidades/${busqueda.id}/pipeline\\?etapas=.+&columna=.+`))
  })

  test('selector de vista y filtro de candidatos viajan en la URL', async ({ page }) => {
    await page.goto('/recruiting/gestion-busquedas')
    await page.locator('#pipeline-vista').selectOption({ label: 'Pipeline individual' })
    await expect(page).toHaveURL(/\/v2\/recruiting\/gestion-busquedas\?vista=individual$/)
    const tarjeta = page.getByTestId('tarjeta-busqueda').filter({ hasText: TITULO })
    await expect(tarjeta).toContainText('2 vacantes')
    await expect(tarjeta).toContainText('Híbrido')
    await expect(tarjeta.getByRole('link', { name: 'Gestionar Pipeline' })).toHaveAttribute('href', `/recruiting/oportunidades/${busqueda.id}/pipeline`)

    await page.locator('#filtro-origen-candidato').selectOption({ label: 'Propios' })
    await expect(page).toHaveURL(/\?vista=individual&alcance_candidatos=propios$/)
    await expect(tarjeta.getByRole('link', { name: 'Gestionar Pipeline' })).toHaveAttribute(
      'href',
      `/recruiting/oportunidades/${busqueda.id}/pipeline?alcance_candidatos=propios`,
    )
    await page.locator('#pipeline-vista').selectOption({ label: 'Vista global' })
    await expect(page).toHaveURL(/\/v2\/recruiting\/gestion-busquedas\?alcance_candidatos=propios$/)
    await expect(page.locator('#filtro-origen-candidato option:checked')).toHaveText('Propios')
  })
})

test.describe('Pipeline de una búsqueda', () => {
  test.describe.configure({ mode: 'serial' })
  test.use({ storageState: estadoDe('autorizado') })

  test('carga inicial: cabecera, contadores, tabla y enlaces con «volver»', async ({ page }) => {
    await abrirPipeline(page, busqueda.id, '?etapas=Oferta&columna=Oferta')
    await expect(page.getByTestId('estado-busqueda')).toHaveText('Abierta')
    await expect(page.getByText('Búsqueda interna')).toBeVisible()
    await expect(page.getByText(CLIENTE).first()).toBeVisible()
    await expect(page.getByText('Vacantes:')).toContainText('2')
    await expect(page.getByText('Híbrido')).toBeVisible()
    await expect(page.getByTestId('total-en-proceso')).toHaveText('3')
    await expect(page.getByTestId('indicador-candidatos')).toHaveText(/Mostrando 4 de 4 candidatos/)
    await expect(page.getByTestId('etapa-Candidato')).toContainText('1')
    await expect(page.getByTestId('etapa-Descartados')).toContainText('1')
    await expect(fila(page, 'avanza').getByTestId('etapa-actual')).toHaveText('Candidato')
    await expect(fila(page, 'avanza')).toContainText('Presentado por:')
    await expect(fila(page, 'descartado')).toContainText('Motivo:')

    const volverPipeline = encodeURIComponent(`/recruiting/oportunidades/${busqueda.id}/pipeline`)
    await expect(page.getByTestId('ver-ficha')).toHaveAttribute(
      'href',
      `/recruiting/oportunidades/${busqueda.id}?volver=${encodeURIComponent(`/recruiting/oportunidades/${busqueda.id}/pipeline?etapas=Oferta&columna=Oferta`)}`,
    )
    // La ficha del candidato vuelve al Pipeline sin el filtro de etapa
    await expect(fila(page, 'avanza').getByRole('link', { name: cands.avanza!.nombre })).toHaveAttribute(
      'href',
      `/recruiting/candidatos/${cands.avanza!.id}?volver=${volverPipeline}`,
    )
    await expect(fila(page, 'avanza').getByRole('link', { name: 'Ver Detalles' })).toHaveAttribute(
      'href',
      `/recruiting/oportunidades/${busqueda.id}/candidatos/${cands.avanza!.id}/detalle?origen=pipeline`,
    )
  })

  test('filtro por etapa y «Ver todas las etapas»', async ({ page }) => {
    await abrirPipeline(page, busqueda.id)
    await page.getByTestId('etapa-Descartados').click()
    await expect(page.getByTestId('fila-candidato')).toHaveCount(1)
    await expect(page.getByTestId('indicador-candidatos')).toHaveText(/Mostrando 1 de 4 candidatos/)
    await expect(fila(page, 'descartado').getByTestId('reingresar')).toBeVisible()
    await page.getByTestId('etapa-Ingreso').click()
    await expect(page.getByText("No hay candidatos en la etapa 'Ingreso'.")).toBeVisible()
    await page.getByRole('button', { name: 'Ver todas las etapas' }).click()
    await expect(page.getByTestId('fila-candidato')).toHaveCount(4)
  })

  test('Escape y un clic afuera cierran los modales sin guardar', async ({ page, monitor }) => {
    await abrirPipeline(page, busqueda.id)
    await fila(page, 'avanza').getByTestId('mover-etapa').click()
    await expect(page.getByTestId('modal-mover')).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(page.getByTestId('modal-mover')).toHaveCount(0)
    await fila(page, 'avanza').getByTestId('descartar').click()
    await expect(page.getByTestId('modal-descartar')).toBeVisible()
    await page.mouse.click(5, 5)
    await expect(page.getByTestId('modal-descartar')).toHaveCount(0)
    expect(monitor.mutacionesDe(/\/etapa$/)).toEqual([])
  })

  test('Mover Etapa a la siguiente con una nota de hasta 50 caracteres', async ({ page, monitor }) => {
    await abrirPipeline(page, busqueda.id)
    await fila(page, 'avanza').getByTestId('mover-etapa').click()
    const modal = page.getByTestId('modal-mover')
    await expect(modal).toContainText(`Candidato: ${cands.avanza!.nombre}`)
    await expect(modal.getByTestId('nueva-etapa').locator('option')).toHaveText(['Screening'])
    await expect(modal.locator('#pretensionSalarialInput')).toBeHidden()
    await modal.locator('#comentarioEtapa').fill('x'.repeat(60))
    await expect(modal.locator('#comentarioEtapa')).toHaveValue('x'.repeat(50))
    await expect(modal.getByText('50/50')).toBeVisible()
    await modal.getByTestId('confirmar-avance').click()

    await expect(toast(page)).toHaveText(`Se movió a ${cands.avanza!.nombre} a la etapa 'Screening'.`)
    await expect(modal).toHaveCount(0)
    await expect(fila(page, 'avanza').getByTestId('etapa-actual')).toHaveText('Screening')
    const guardado = await filaEnBackend(busqueda.id, 'avanza')
    expect(guardado.etapa_actual).toBe('Screening')
    expect(guardado.feedback_etapa).toBe('x'.repeat(50))
    expect(monitor.mutacionesDe(/PUT \/recruiting\/oportunidades\/.+\/etapa$/)).toHaveLength(1)
  })

  test('de Entrevista RRHH a Líder la pretensión es obligatoria y se guarda como entero', async ({ page }) => {
    await abrirPipeline(page, busqueda.id)
    await fila(page, 'rrhh').getByTestId('mover-etapa').click()
    const modal = page.getByTestId('modal-mover')
    await expect(modal.getByTestId('nueva-etapa')).toHaveValue('Entrevista Líder Dicsys')
    const pretension = modal.locator('#pretensionSalarialInput')
    await expect(pretension).toBeVisible()
    await modal.getByTestId('confirmar-avance').click()
    await expect(modal.getByTestId('error-pretension')).toHaveText('La pretensión salarial es obligatoria.')
    await expect(modal).toBeVisible()

    await pretension.pressSequentially('1500000')
    await expect(pretension).toHaveValue('$ 1.500.000')
    await modal.getByTestId('confirmar-avance').click()
    await expect(toast(page)).toHaveText(`Se movió a ${cands.rrhh!.nombre} a la etapa 'Entrevista Líder Dicsys'.`)
    const guardado = await filaEnBackend(busqueda.id, 'rrhh')
    expect(guardado.etapa_actual).toBe('Entrevista Líder Dicsys')
    expect(guardado.pretension_salarial_bruta_ars).toBe(1500000)
  })

  test('Mover Etapa con un archivo adjunto (un formato no admitido se descarta)', async ({ page }) => {
    await abrirPipeline(page, busqueda.id)
    await fila(page, 'adjunto').getByTestId('mover-etapa').click()
    const modal = page.getByTestId('modal-mover')
    await expect(modal.getByTestId('nueva-etapa').locator('option')).toHaveText(['Examen Médico Preocupacional'])

    await modal.getByTestId('archivo-etapa').setInputFiles({ name: 'programa.exe', mimeType: 'application/octet-stream', buffer: Buffer.from('x') })
    await expect(modal.getByTestId('archivo-elegido')).toHaveCount(0)
    await expect(modal.getByText('Opcional (PDF, DOCX, imágenes, etc. Máx 10 MB)')).toBeVisible()

    await modal.getByTestId('archivo-etapa').setInputFiles({ name: 'oferta-firmada.pdf', mimeType: 'application/pdf', buffer: crearPdf(['Oferta E2E']) })
    await expect(modal.getByTestId('archivo-elegido')).toContainText('oferta-firmada.pdf')
    await expect(modal.getByRole('button', { name: 'Cambiar archivo' })).toBeVisible()
    await modal.getByTestId('confirmar-avance').click()

    await expect(toast(page)).toHaveText(
      `Se movió a ${cands.adjunto!.nombre} a la etapa 'Examen Médico Preocupacional' con archivo adjunto.`,
    )
    expect((await filaEnBackend(busqueda.id, 'adjunto')).etapa_actual).toBe('Examen Médico Preocupacional')
    const archivos = await api.get<{ nombre_archivo: string; etapa_id: string }[]>(
      `/recruiting/oportunidades/${busqueda.id}/candidatos/${cands.adjunto!.id}/archivos-etapa`,
    )
    expect(archivos.map((a) => [a.nombre_archivo, a.etapa_id])).toEqual([['oferta-firmada.pdf', 'Examen Médico Preocupacional']])
  })

  test('Descartar con un motivo de la etapa del candidato', async ({ page }) => {
    await abrirPipeline(page, busqueda.id)
    await fila(page, 'avanza').getByTestId('descartar').click()
    const modal = page.getByTestId('modal-descartar')
    await expect(modal).toContainText('Etapa activa de descarte: Screening')
    const combo = modal.getByTestId('motivo-descarte')
    await expect(combo).toBeVisible()
    const motivo = (await combo.locator('option:checked').innerText()).trim()
    expect(motivo).not.toBe('')
    await modal.locator('#comentarioDescarte').fill('No continua')
    await modal.getByTestId('confirmar-descarte').click()

    await expect(toast(page)).toHaveText(`El candidato ${cands.avanza!.nombre} fue marcado como descartado.`)
    await expect(fila(page, 'avanza')).toContainText(`Motivo: ${motivo}`)
    await expect(fila(page, 'avanza').getByTestId('reingresar')).toBeVisible()
    const guardado = await filaEnBackend(busqueda.id, 'avanza')
    expect([guardado.etapa_actual, guardado.estado, guardado.motivo_descarte]).toEqual(['Descartados', 'Descartado', motivo])
  })

  test('Reingresar al proceso exige el motivo y vuelve a Entrevista RRHH', async ({ page }) => {
    await abrirPipeline(page, busqueda.id)
    await fila(page, 'descartado').getByTestId('reingresar').click()
    const modal = page.getByTestId('modal-reingresar')
    await expect(modal.locator('#etapaReingreso')).toHaveValue('Entrevista RRHH')
    await expect(modal.getByTestId('confirmar-reingreso')).toBeDisabled()
    await modal.getByTestId('motivo-reingreso').fill('   ')
    await expect(modal.getByTestId('confirmar-reingreso')).toBeDisabled()
    await modal.getByTestId('motivo-reingreso').fill('Se flexibilizo el seniority')
    await modal.getByTestId('confirmar-reingreso').click()

    await expect(toast(page)).toHaveText(`El candidato ${cands.descartado!.nombre} reingresó exitosamente al proceso en 'Entrevista RRHH'.`)
    await expect(fila(page, 'descartado').getByTestId('etapa-actual')).toHaveText('Entrevista RRHH')
    await expect(fila(page, 'descartado')).not.toContainText('Motivo:')
    const guardado = await filaEnBackend(busqueda.id, 'descartado')
    expect([guardado.etapa_actual, guardado.estado, guardado.motivo_descarte]).toEqual(['Entrevista RRHH', 'En proceso', null])
  })
})

test.describe('Ingreso cierra la búsqueda como Ganada', () => {
  test.use({ storageState: estadoDe('autorizado') })

  test('al confirmar el Ingreso la búsqueda queda Ganada y solo de consulta', async ({ page }) => {
    await abrirPipeline(page, ganable.id)
    await expect(fila(page, 'activoGanada').getByTestId('mover-etapa')).toBeEnabled()
    await fila(page, 'examen').getByTestId('mover-etapa').click()
    const modal = page.getByTestId('modal-mover')
    await expect(modal.getByTestId('nueva-etapa')).toHaveValue('Ingreso')
    const recarga = page.waitForEvent('load', { timeout: 15_000 })
    await modal.getByTestId('confirmar-avance').click()
    await expect(toast(page)).toHaveText(`Se movió a ${cands.examen!.nombre} a Ingreso. La búsqueda quedó Ganada y cerrada.`)

    // Se recarga sola y queda bloqueada
    await recarga
    await expect(page.getByTestId('pipeline-titulo')).toBeVisible()
    await expect(page.getByTestId('aviso-busqueda-ganada')).toBeVisible()
    await expect(page.getByTestId('estado-busqueda')).toHaveText('Ganada')
    await expect(fila(page, 'examen')).toContainText('Ingreso Confirmado')
    const mover = fila(page, 'activoGanada').getByTestId('mover-etapa')
    await expect(mover).toBeDisabled()
    await expect(mover).toHaveAttribute('title', 'La búsqueda está Ganada y cerrada')
    await expect(fila(page, 'activoGanada').getByTestId('descartar')).toBeDisabled()
    await expect(fila(page, 'descartadoGanada').getByTestId('reingresar')).toHaveCount(0)
    const op = await api.get<{ estado: string }>(`/recruiting/oportunidades/${ganable.id}`)
    expect(op.estado).toBe('Ganada')
  })
})
