import { execFileSync } from 'node:child_process'
import { mkdirSync, writeFileSync } from 'node:fs'
import path from 'node:path'

import type { Page, Route } from '@playwright/test'

import { ADMIN, ClienteApi } from '../api'
import { crearPdf, textoCv } from '../archivos'
import { estadoDe, expect, ingresar, SALIDA, test, type Credencial } from '../fixtures'
import { COMPOSE, RAIZ } from '../stack'

/**
 * Parámetros de Recruiting (11 pantallas Vue). Criterio legacy: plantillas recruiting/parametros.html, skills.html,
 * habilidades.html, provincias.html, ciudades.html, lideres.html, reclutadores.html, perfiles_profesionales.html,
 * motivos_blacklist.html, archivos_cv.html e historial_cargas_cv.html (títulos, columnas, botones y textos se comparan
 * con esas plantillas, que ya no se pueden abrir: sus URLs redirigen a la SPA).
 *
 * Todo corre contra el stack AISLADO (base en tmpfs). El ABM crea, edita y da de baja datos descartables de esa base.
 * Backup, importación, restauración y limpieza NO llegan al servidor: se responden con mocks de red (page.route) y
 * cualquier otra llamada a esas rutas se corta.
 */

const CAPTURAS = path.join(SALIDA, 'capturas-parametros')
mkdirSync(CAPTURAS, { recursive: true })
const capturar = (page: Page, nombre: string) => page.screenshot({ path: path.join(CAPTURAS, `${nombre}.png`), fullPage: true })

const SUFIJO = Date.now().toString(36)

// ---- Datos del entorno aislado -------------------------------------------------------------------------------------

/** Usuario NO administrador con el ítem Parámetros (creado en la base aislada). */
let credencialParametros: Credencial | null = null
async function usuarioParametros(): Promise<Credencial> {
  if (credencialParametros) return credencialParametros
  const admin = await ClienteApi.ingresar(ADMIN.email, ADMIN.password)
  const grupo = await admin.post<{ id: string }>('/permisos/grupos', { nombre: `Parametros E2E ${SUFIJO}`, descripcion: 'E2E Parametros' })
  await admin.put(`/permisos/grupos/${grupo.id}/permisos`, {
    permisos: ['recruiting', 'recruiting.parametros'].map((modulo) => ({ modulo, tiene_acceso: true })),
  })
  const email = `parametros.${SUFIJO}.e2e@dicsys.com`
  const password = 'E2e-Usuario-2026!'
  await admin.post('/usuarios', { email, nombre: 'Parametros', apellido: 'E2E', password, rol: 'usuario', grupo_ids: [grupo.id] })
  credencialParametros = { email, password, estado: 'parametros' }
  return credencialParametros
}

/** Archivos ficticios en las carpetas de CV del backend AISLADO (tmpfs del contenedor e2e-backend). */
let archivosSembrados = false
function sembrarArchivosCv(): void {
  if (archivosSembrados) return
  const script = [
    'set -e',
    'R=/tmp/e2e/cv',
    'mkdir -p $R/cv_procesados_ok $R/cv_errores $R/cv_duplicados',
    // 25 archivos con fechas crecientes: el más reciente (25) va primero
    'for i in $(seq -w 1 25); do printf "%%PDF-1.4 e2e $i" > $R/cv_procesados_ok/e2e_param_$i.pdf; touch -d "2026-01-01 00:00:$i" $R/cv_procesados_ok/e2e_param_$i.pdf; done',
    'printf "x" > $R/cv_errores/e2e_param_error.pdf',
  ].join('\n')
  execFileSync('docker', [...COMPOSE, 'exec', '-T', 'e2e-backend', 'sh', '-c', script], { cwd: RAIZ, encoding: 'utf8' })
  archivosSembrados = true
}

/** Dos operaciones de carga individual reales en la base aislada (una válida y una sin email) para el historial. */
let historialSembrado = false
async function sembrarHistorial(): Promise<void> {
  if (historialSembrado) return
  const admin = await ClienteApi.ingresar(ADMIN.email, ADMIN.password)
  await admin.subirArchivo(
    '/recruiting/candidatos/cargar-cv',
    'cv-parametros-e2e.pdf',
    crearPdf(textoCv({ nombre: 'Paula', apellido: 'Parametro', email: `paula.parametro.${SUFIJO}@example.com` })),
  )
  try {
    await admin.subirArchivo('/recruiting/candidatos/cargar-cv', 'cv-sin-email-e2e.pdf', crearPdf(['Sin datos de contacto', 'Texto']))
  } catch {
    // el backend la rechaza (sin email): igual queda en el historial como fallida
  }
  historialSembrado = true
}

// ---- Utilidades ----------------------------------------------------------------------------------------------------

const aviso = (page: Page, texto: string | RegExp) => page.getByRole('status').filter({ hasText: texto })
const filaAbm = (page: Page, texto: string) => page.locator('table tbody tr', { hasText: texto })
const aceptarConfirm = (page: Page) => page.once('dialog', (d) => void d.accept())

async function esperarTabla(page: Page): Promise<void> {
  await expect(page.locator('table thead')).toBeVisible()
  await expect(page.locator('table tbody .animate-spin')).toHaveCount(0)
}

const PESTANAS = [
  'Porcentaje de Aceptación',
  'Skills / Tecnologías',
  'Habilidades / Competencias',
  'Provincias',
  'Ciudades',
  'Líderes / Hiring Managers',
  'Reclutadores',
  'Perfiles profesionales',
  'Motivos de Blacklist',
  'Archivos de CV',
  'Historial de cargas de CV',
]

/** Pantallas: URL de siempre, ruta de la SPA, título de la pestaña del navegador y encabezado h2 (legacy). */
const PANTALLAS = [
  { clave: 'config', legacy: '/recruiting/parametros', titulo: 'Parámetros - Recruiting', h2: 'Porcentaje de Aceptación (Smart Matching)' },
  { clave: 'skills', legacy: '/recruiting/parametros/skills', titulo: 'Skills - Parámetros de Recruiting', h2: 'Catálogo de Skills y Tecnologías' },
  { clave: 'habilidades', legacy: '/recruiting/parametros/habilidades', titulo: 'Habilidades - Parámetros de Recruiting', h2: 'Catálogo de Habilidades y Competencias' },
  { clave: 'provincias', legacy: '/recruiting/parametros/provincias', titulo: 'Provincias - Parámetros de Recruiting', h2: 'Catálogo de Provincias' },
  { clave: 'ciudades', legacy: '/recruiting/parametros/ciudades', titulo: 'Ciudades - Parámetros de Recruiting', h2: 'Catálogo de Ciudades' },
  { clave: 'lideres', legacy: '/recruiting/parametros/lideres', titulo: 'Líderes - Parámetros de Recruiting', h2: 'Catálogo de Líderes / Hiring Managers' },
  { clave: 'reclutadores', legacy: '/recruiting/parametros/reclutadores', titulo: 'Reclutadores - Parámetros de Recruiting', h2: 'Catálogo de Reclutadores responsables' },
  { clave: 'perfiles', legacy: '/recruiting/parametros/perfiles-profesionales', titulo: 'Perfiles profesionales - Parámetros de Recruiting', h2: 'Catálogo de Perfiles profesionales' },
  { clave: 'motivos', legacy: '/recruiting/parametros/motivos-blacklist', titulo: 'Motivos de Blacklist - Parámetros de Recruiting', h2: 'Catálogo de Motivos de Blacklist' },
  { clave: 'archivos', legacy: '/recruiting/parametros/archivos-cv', titulo: 'Archivos de CV - Parámetros de Recruiting', h2: 'Archivos de CV' },
  { clave: 'historial', legacy: '/recruiting/parametros/historial-cargas-cv', titulo: 'Historial de cargas de CV - Parámetros de Recruiting', h2: 'Historial de cargas de CV' },
] as const

// =====================================================================================================================
// Administrador: carga, navegación, redirecciones y paridad visual de las 11 pantallas
// =====================================================================================================================

test.describe('administrador: carga y navegación', () => {
  test.use({ storageState: estadoDe('admin') })
  test.beforeAll(async () => {
    sembrarArchivosCv()
    await sembrarHistorial()
  })

  for (const p of PANTALLAS) {
    test(`${p.clave}: la URL de siempre redirige a la SPA conservando los parámetros y la pantalla carga`, async ({ page }) => {
      await page.goto(`${p.legacy}?q=e2e`)
      await expect(page).toHaveURL(new RegExp(`/v2${p.legacy.replace(/\//g, '\\/')}\\?q=e2e$`))
      await expect(page.locator('h1', { hasText: 'Parámetros' })).toBeVisible()
      await expect(page.locator('h2', { hasText: p.h2 }).first()).toBeVisible()
      await expect(page).toHaveTitle(`${p.titulo} - Dicsys Core`)
      // Las 11 pestañas de la interfaz anterior, en el mismo orden, con la activa resaltada
      const pestanas = page.getByTestId('parametros-pestanas').locator('a')
      await expect(pestanas).toHaveText(PESTANAS.map((n) => new RegExp(n.replace(/[/()]/g, '\\$&'))))
      await expect(pestanas.filter({ hasText: PESTANAS[PANTALLAS.indexOf(p)]! })).toHaveClass(/border-primary-600/)
      if (p.clave !== 'config' && p.clave !== 'archivos' && p.clave !== 'historial') await esperarTabla(page)
      await capturar(page, `admin-${p.clave}`)
    })
  }

  test('acceso directo por URL /v2 (200) y navegación por pestañas sin recargar la página', async ({ page }) => {
    const r = await page.goto('/v2/recruiting/parametros')
    expect(r?.status()).toBe(200)
    await page.evaluate(() => ((window as unknown as { __marca: number }).__marca = 1))
    for (const [i, p] of PANTALLAS.entries()) {
      await page.getByTestId('parametros-pestanas').locator('a', { hasText: PESTANAS[i]! }).click()
      await expect(page).toHaveURL(new RegExp(`/v2${p.legacy}$`))
      await expect(page.locator('h2', { hasText: p.h2 }).first()).toBeVisible()
    }
    // Navegación interna de la SPA: la marca sigue (no hubo recarga completa)
    expect(await page.evaluate(() => (window as unknown as { __marca?: number }).__marca)).toBe(1)
  })

  test('el menú lateral resalta «Parámetros» en verde', async ({ page }) => {
    await page.goto('/v2/recruiting/parametros/skills')
    const item = page.locator('aside a', { hasText: 'Parámetros' }).first()
    await expect(item).toHaveClass(/emerald/)
  })
})

// =====================================================================================================================
// Configuración (Smart Matching)
// =====================================================================================================================

test.describe('Configuración Smart Matching', () => {
  test.use({ storageState: estadoDe('admin') })
  test.describe.configure({ mode: 'serial' })

  test('muestra el valor real, valida el rango y guarda en el backend (se restaura al final)', async ({ page, monitor }) => {
    const admin = await ClienteApi.ingresar(ADMIN.email, ADMIN.password)
    const original = (await admin.get<{ match_minimo_porcentaje: number }>('/recruiting/parametros/config')).match_minimo_porcentaje
    await page.goto('/recruiting/parametros')
    const numero = page.locator('input[type="number"]')
    await expect(numero).toHaveValue(String(original))
    await expect(page.getByText(`≥ ${original}%`)).toBeVisible()

    for (const invalido of ['0', '101', '']) {
      await numero.fill(invalido)
      await page.getByRole('button', { name: 'Guardar cambios' }).click()
      await expect(aviso(page, 'El valor debe estar entre 1 y 100.')).toBeVisible()
    }
    expect(monitor.mutacionesDe(/PUT .*\/config$/)).toHaveLength(0)

    const nuevo = original === 61 ? 62 : 61
    await numero.fill(String(nuevo))
    await expect(page.locator('input[type="range"]')).toHaveValue(String(nuevo))
    await page.getByRole('button', { name: 'Guardar cambios' }).click()
    await expect(aviso(page, 'Configuración guardada correctamente.')).toBeVisible()
    expect((await admin.get<{ match_minimo_porcentaje: number }>('/recruiting/parametros/config')).match_minimo_porcentaje).toBe(nuevo)
    await capturar(page, 'config-guardada')

    await admin.put('/recruiting/parametros/config', { match_minimo_porcentaje: original })
  })

  test('sin el valor real (error al cargar) no deja guardar el 50 de presentación', async ({ page, monitor }) => {
    monitor.permitir(/^500 GET \/api\/v1\/recruiting\/parametros\/config$/)
    await page.route('**/api/v1/recruiting/parametros/config', (r) =>
      r.request().method() === 'GET' ? r.fulfill({ status: 500, json: { detail: 'Fallo simulado' } }) : r.continue(),
    )
    await page.goto('/v2/recruiting/parametros')
    await expect(aviso(page, 'Fallo simulado')).toBeVisible({ timeout: 15_000 })
    await expect(page.getByRole('button', { name: 'Guardar cambios' })).toBeDisabled()
  })
})

// =====================================================================================================================
// Catálogos ABM: alta, edición, estado y baja con datos descartables de la base aislada; paridad con legacy
// =====================================================================================================================

interface CatalogoPrueba {
  ruta: string
  nuevo: string
  columnas: string[]
  buscar?: string
  placeholder: string
  extra?: { placeholder: string; valor: string }
  logica: boolean
  creado: string
  actualizado: string
  baja: (n: string) => string
  estado?: (n: string, activo: boolean) => string
}

const CATALOGOS: CatalogoPrueba[] = [
  {
    ruta: 'skills', nuevo: 'Nuevo Skill', columnas: ['Nombre', 'Categoría', 'Estado', 'Acciones'], buscar: 'Buscar por nombre...',
    placeholder: 'Ej: React, Python, Docker, etc.', extra: { placeholder: 'Ej: Lenguajes, Frontend, Backend, DevOps, etc.', valor: 'Categoria E2E' },
    logica: true, creado: 'Skill creado exitosamente.', actualizado: 'Skill actualizado correctamente.',
    baja: (n) => `Skill '${n}' desactivado exitosamente.`, estado: (n, a) => `Skill '${n}' ${a ? 'activado' : 'desactivado'}.`,
  },
  {
    ruta: 'habilidades', nuevo: 'Nueva Habilidad', columnas: ['Nombre / Rol', 'Categoría', 'Estado', 'Acciones'], buscar: 'Buscar por competencia...',
    placeholder: 'Ej: Liderazgo, Negociación, Proactividad, etc.', extra: { placeholder: 'Ej: Comunicación, Liderazgo, Gestión, etc.', valor: 'Categoria E2E' },
    logica: true, creado: 'Habilidad creada exitosamente.', actualizado: 'Habilidad actualizada correctamente.',
    baja: (n) => `Habilidad '${n}' desactivada exitosamente.`, estado: (n, a) => `Habilidad '${n}' ${a ? 'activada' : 'desactivada'}.`,
  },
  {
    ruta: 'lideres', nuevo: 'Nuevo Líder', columnas: ['Nombre', 'Estado', 'Acciones'], buscar: 'Buscar por nombre...', placeholder: 'Ej: Maria Jose Padin',
    logica: true, creado: 'Líder creado exitosamente.', actualizado: 'Líder actualizado correctamente.',
    baja: (n) => `'${n}' desactivado exitosamente.`, estado: (n, a) => `'${n}' ${a ? 'activado' : 'desactivado'}.`,
  },
  {
    ruta: 'reclutadores', nuevo: 'Nuevo Reclutador', columnas: ['Nombre', 'Estado', 'Acciones'], buscar: 'Buscar por nombre...', placeholder: 'Ej: Ana',
    logica: true, creado: 'Reclutador creado exitosamente.', actualizado: 'Reclutador actualizado correctamente.',
    baja: (n) => `'${n}' desactivado exitosamente.`, estado: (n, a) => `'${n}' ${a ? 'activado' : 'desactivado'}.`,
  },
  {
    ruta: 'perfiles-profesionales', nuevo: 'Nuevo Perfil', columnas: ['Nombre', 'Estado', 'Acciones'], buscar: 'Buscar por nombre...', placeholder: 'Ej: Analista de Datos',
    logica: true, creado: 'Perfil profesional creado exitosamente.', actualizado: 'Perfil profesional actualizado correctamente.',
    baja: (n) => `'${n}' desactivado exitosamente.`, estado: (n, a) => `'${n}' ${a ? 'activado' : 'desactivado'}.`,
  },
  {
    ruta: 'motivos-blacklist', nuevo: 'Nuevo Motivo', columnas: ['Motivo', 'Acciones'], placeholder: 'Ej: Conducta inapropiada',
    logica: false, creado: 'Motivo creado exitosamente.', actualizado: 'Motivo actualizado correctamente.',
    baja: (n) => `Motivo '${n}' eliminado exitosamente.`,
  },
]

test.describe('catálogos ABM', () => {
  test.use({ storageState: estadoDe('admin') })

  for (const c of CATALOGOS) {
    test(`${c.ruta}: columnas y textos de la interfaz anterior, alta, búsqueda, edición, estado y baja`, async ({ page, monitor }) => {
      const nombre = `${c.ruta} E2E ${SUFIJO}`
      const editado = `${nombre} editado`
      await page.goto(`/recruiting/parametros/${c.ruta}`)
      await esperarTabla(page)
      await expect(page.locator('table thead th')).toHaveText(c.columnas)
      if (c.buscar) await expect(page.getByPlaceholder(c.buscar)).toBeVisible()

      // Alta: el modal enfoca el primer campo; la tabla no vuelve al spinner al refrescar (M4)
      await page.getByRole('button', { name: c.nuevo }).click()
      const dialogo = page.getByRole('dialog')
      await expect(dialogo).toBeVisible()
      await expect(dialogo.getByPlaceholder(c.placeholder)).toBeFocused()
      // Obligatorio vacío: la validación del formulario no deja enviarlo
      await dialogo.locator('button[type="submit"]').click()
      await expect(dialogo).toBeVisible()
      expect(monitor.mutaciones).toHaveLength(0)
      await dialogo.getByPlaceholder(c.placeholder).fill(nombre)
      if (c.extra) await dialogo.getByPlaceholder(c.extra.placeholder).fill(c.extra.valor)
      await page.evaluate(() => {
        const w = window as unknown as { __spinner: boolean }
        w.__spinner = false
        new MutationObserver(() => {
          if (document.querySelector('table tbody .animate-spin')) w.__spinner = true
        }).observe(document.body, { subtree: true, childList: true })
      })
      await dialogo.locator('button[type="submit"]').click()
      await expect(aviso(page, c.creado)).toBeVisible()
      await expect(dialogo).toHaveCount(0)
      await expect(filaAbm(page, nombre)).toHaveCount(1)
      expect(await page.evaluate(() => (window as unknown as { __spinner: boolean }).__spinner), 'spinner al refrescar').toBe(false)
      if (c.extra) await expect(filaAbm(page, nombre)).toContainText(c.extra.valor)

      // Búsqueda local
      if (c.buscar) {
        await page.getByPlaceholder(c.buscar).fill(`E2E ${SUFIJO}`)
        await expect(page.locator('table tbody tr')).toHaveCount(1)
        await page.getByPlaceholder(c.buscar).fill('zzz-no-existe-e2e')
        await expect(page.locator('table tbody')).toContainText('Probá con otro término de búsqueda.')
        await page.getByRole('button', { name: 'Limpiar búsqueda' }).click()
      }

      // Edición: Escape cierra sin guardar; después se guarda
      await filaAbm(page, nombre).getByRole('button', { name: 'Editar' }).click()
      await expect(dialogo.getByPlaceholder(c.placeholder)).toHaveValue(nombre)
      await page.keyboard.press('Escape')
      await expect(dialogo).toHaveCount(0)
      await filaAbm(page, nombre).getByRole('button', { name: 'Editar' }).click()
      await dialogo.getByPlaceholder(c.placeholder).fill(editado)
      await dialogo.getByRole('button', { name: 'Guardar Cambios' }).click()
      await expect(aviso(page, c.actualizado)).toBeVisible()
      await expect(filaAbm(page, editado)).toHaveCount(1)
      await capturar(page, `abm-${c.ruta}`)

      if (c.logica) {
        // Baja lógica y reactivación desde el chip de estado
        aceptarConfirm(page)
        await filaAbm(page, editado).getByRole('button', { name: 'Desactivar' }).click()
        await expect(aviso(page, c.baja(editado))).toBeVisible()
        await expect(filaAbm(page, editado)).toContainText('Inactivo')
        await expect(filaAbm(page, editado).getByRole('button', { name: 'Desactivar' })).toHaveCount(0)
        await filaAbm(page, editado).getByRole('button', { name: 'Inactivo' }).click()
        await expect(aviso(page, c.estado!(editado, true))).toBeVisible()
        await expect(filaAbm(page, editado)).toContainText('Activo')
        // se deja inactivo (dato descartable de la base aislada)
        await filaAbm(page, editado).getByRole('button', { name: 'Activo', exact: true }).click()
        await expect(aviso(page, c.estado!(editado, false))).toBeVisible()
      } else {
        // Confirmación rechazada: no borra; aceptada: borra
        page.once('dialog', (d) => void d.dismiss())
        await filaAbm(page, editado).getByRole('button', { name: 'Eliminar' }).click()
        await expect(filaAbm(page, editado)).toHaveCount(1)
        aceptarConfirm(page)
        await filaAbm(page, editado).getByRole('button', { name: 'Eliminar' }).click()
        await expect(aviso(page, c.baja(editado))).toBeVisible()
        await expect(filaAbm(page, editado)).toHaveCount(0)
      }
      // Todas las mutaciones fueron al proxy /api/v1 de este catálogo
      const ruta = c.ruta === 'perfiles-profesionales' ? 'perfiles-puesto' : c.ruta
      for (const m of monitor.mutaciones) expect(m.url).toMatch(new RegExp(`^/api/v1/recruiting/parametros/${ruta}`))
    })
  }

  test('provincias y ciudades: alta encadenada, filtro por provincia, contador actualizado entre pestañas (M5) y bajas', async ({ page }) => {
    const provincia = `Provincia E2E ${SUFIJO}`
    const ciudad = `Ciudad E2E ${SUFIJO}`
    await page.goto('/recruiting/parametros/provincias')
    await esperarTabla(page)
    await expect(page.locator('table thead th')).toHaveText(['Provincia', 'Ciudades', 'Acciones'])
    await page.getByRole('button', { name: 'Nueva Provincia' }).click()
    await page.getByRole('dialog').getByPlaceholder('Ej: Cordoba').fill(provincia)
    await page.getByRole('dialog').getByRole('button', { name: 'Crear Provincia' }).click()
    await expect(aviso(page, 'Provincia creada exitosamente.')).toBeVisible()
    await expect(filaAbm(page, provincia).locator('td').nth(1)).toHaveText('0')

    // Ciudades por la pestaña (navegación interna: la caché de provincias tiene que refrescarse)
    await page.getByTestId('parametros-pestanas').locator('a', { hasText: 'Ciudades' }).click()
    await esperarTabla(page)
    await expect(page.locator('table thead th')).toHaveText(['Ciudad', 'Provincia', 'Acciones'])
    const filtro = page.getByLabel('Filtrar por provincia')
    await expect(filtro.locator('option', { hasText: provincia })).toHaveCount(1)
    await page.getByRole('button', { name: 'Nueva Ciudad' }).click()
    const dialogo = page.getByRole('dialog')
    await dialogo.locator('select').selectOption({ label: provincia })
    await dialogo.getByPlaceholder('Ej: Villa Carlos Paz').fill(ciudad)
    await dialogo.getByRole('button', { name: 'Crear Ciudad' }).click()
    await expect(aviso(page, 'Ciudad creada exitosamente.')).toBeVisible()
    await expect(filaAbm(page, ciudad)).toContainText(provincia)

    // Filtro por provincia: pide al backend y deja solo esa ciudad
    const pedido = page.waitForRequest((r) => /\/api\/v1\/recruiting\/parametros\/ciudades\?provincia_id=\d+/.test(r.url()))
    await filtro.selectOption({ label: provincia })
    await pedido
    await expect(page.locator('table tbody tr')).toHaveCount(1)
    await expect(filaAbm(page, ciudad)).toHaveCount(1)
    await capturar(page, 'abm-ciudades-filtrado')

    // Vuelta a Provincias por la pestaña: el contador ya cuenta la ciudad nueva
    await page.getByTestId('parametros-pestanas').locator('a', { hasText: 'Provincias' }).click()
    await expect(filaAbm(page, provincia).locator('td').nth(1)).toHaveText('1')

    // Bajas (datos descartables): ciudad y después provincia
    await page.getByTestId('parametros-pestanas').locator('a', { hasText: 'Ciudades' }).click()
    await esperarTabla(page)
    aceptarConfirm(page)
    await filaAbm(page, ciudad).getByRole('button', { name: 'Eliminar' }).click()
    await expect(aviso(page, `Ciudad '${ciudad}' eliminada exitosamente.`)).toBeVisible()
    await page.getByTestId('parametros-pestanas').locator('a', { hasText: 'Provincias' }).click()
    await expect(filaAbm(page, provincia).locator('td').nth(1)).toHaveText('0')
    aceptarConfirm(page)
    await filaAbm(page, provincia).getByRole('button', { name: 'Eliminar' }).click()
    await expect(aviso(page, `Provincia '${provincia}' eliminada exitosamente.`)).toBeVisible()
    await expect(filaAbm(page, provincia)).toHaveCount(0)
  })
})

// =====================================================================================================================
// Archivos de CV: listado, búsqueda, paginación y descarga reales (carpetas del backend aislado); diálogos con mocks
// =====================================================================================================================

const BACKUP_ID = 'bk-e2e'
const IMPORTACION_ID = 'imp-e2e'
const RESUMEN_LIMPIEZA = { registros: { recruiting_candidatos: 3 }, archivos: { cv_procesados_ok: 2 }, total_registros: 3, total_archivos: 2 }

function importacion(estado: string, extra: Record<string, unknown> = {}) {
  return {
    importacion_id: IMPORTACION_ID, estado, fase: estado === 'restaurando' ? 'base_de_datos' : null, porcentaje: estado === 'finalizado' ? 100 : 50,
    mensaje: `Mock ${estado}`, error: null, nombre_original: 'backup-e2e.zip', tamano: '1 KB',
    preview: {
      integridad: { detalle: 'SHA-256 verificado (mock)' }, generado_utc: '2026-11-19 12:00:00', version_backup: '1', generado_por: 'admin@admin.com',
      tamano_total: '1 KB', tamano_zip: '1 KB', total_registros: 3, total_tablas: 1,
      carpetas: [{ carpeta: 'cv_procesados_ok', cantidad: 2, tamano: '1 KB' }], tablas: [{ tabla: 'recruiting_candidatos', registros: 3 }],
    },
    limitaciones: [], avisos: [], backup_seguridad: null, resultado: null, revertido: null, ...extra,
  }
}

/** Mocks de backup, importación y limpieza. Lo que no tenga mock (y apunte a esas rutas) se corta: nunca llega al servidor. */
async function mockearOperacionesDestructivas(page: Page, finalizado: Record<string, unknown>): Promise<string[]> {
  const cortadas: string[] = []
  await page.route(/\/(limpiar-bd|backup\/|importar\/)/, (r: Route) => {
    cortadas.push(`${r.request().method()} ${new URL(r.request().url()).pathname}`)
    return r.abort()
  })
  await page.route('**/api/v1/recruiting/parametros/archivos-cv/backup/iniciar', (r) =>
    r.fulfill({ status: 202, json: { backup_id: BACKUP_ID, estado: 'generando', fase: 'archivos', porcentaje: 40, mensaje: 'Copiando (mock)', nombre_archivo: null, tamano: null, sha256: null, error: null } }),
  )
  await page.route(`**/api/v1/recruiting/parametros/archivos-cv/backup/${BACKUP_ID}/estado`, (r) =>
    r.fulfill({ json: { backup_id: BACKUP_ID, estado: 'finalizado', fase: null, porcentaje: 100, mensaje: 'Listo (mock)', nombre_archivo: 'recruiting-backup-e2e.zip', tamano: '1,00 KB', sha256: 'abc123', error: null } }),
  )
  await page.route('**/recruiting/parametros/archivos-cv/importar/subir', (r) => r.fulfill({ status: 202, json: { success: true, importacion: importacion('validado') } }))
  await page.route(`**/api/v1/recruiting/parametros/archivos-cv/importar/${IMPORTACION_ID}/confirmar`, (r) => r.fulfill({ status: 202, json: importacion('restaurando') }))
  await page.route(`**/api/v1/recruiting/parametros/archivos-cv/importar/${IMPORTACION_ID}/estado`, (r) => r.fulfill({ json: finalizado }))
  await page.route(`**/api/v1/recruiting/parametros/archivos-cv/importar/${IMPORTACION_ID}`, (r) => r.fulfill({ json: { ok: true } }))
  await page.route('**/recruiting/parametros/archivos-cv/limpiar-bd', (r) => r.fulfill({ json: { success: true, resumen: RESUMEN_LIMPIEZA } }))
  return cortadas
}

const zipFicticio = { name: 'backup-e2e.zip', mimeType: 'application/zip', buffer: Buffer.from('PK\u0005\u0006' + '\u0000'.repeat(18), 'latin1') }

test.describe('Archivos de CV (administrador)', () => {
  test.use({ storageState: estadoDe('admin') })
  test.beforeAll(() => sembrarArchivosCv())

  test('tarjetas, listado, búsqueda, paginación y descarga', async ({ page }) => {
    const admin = await ClienteApi.ingresar(ADMIN.email, ADMIN.password)
    const resumen = await admin.get<{ carpeta: string; cantidad_archivos: number }[]>('/recruiting/parametros/archivos-cv')
    const ok = resumen.find((c) => c.carpeta === 'cv_procesados_ok')!.cantidad_archivos
    expect(ok).toBeGreaterThanOrEqual(25)

    await page.goto('/recruiting/parametros/archivos-cv')
    // Como antes: solo «Procesados correctamente» y «Con errores» (cv_duplicados no se muestra)
    await expect(page.getByTestId('archivos-cv-tarjeta-cv_procesados_ok')).toBeVisible()
    await expect(page.getByTestId('archivos-cv-tarjeta-cv_errores')).toBeVisible()
    await expect(page.getByTestId('archivos-cv-tarjeta-cv_duplicados')).toHaveCount(0)
    await expect(page.getByTestId('archivos-cv-tarjeta-cv_procesados_ok').getByTestId('archivos-cv-cantidad')).toHaveText(String(ok))
    await expect(page.getByTestId('archivos-cv-carpeta-seleccionada')).toHaveText('cv_procesados_ok')
    await expect(page.getByTestId('archivos-cv-tabla').locator('thead th')).toHaveText(['Nombre', 'Tamaño', 'Última modificación', 'Descargar'])
    await expect(page.getByTestId('archivos-cv-fila')).toHaveCount(20)
    const paginas = Math.ceil(ok / 20)
    await expect(page.getByTestId('archivos-cv-pagina')).toHaveText(`Página 1 de ${paginas}`)
    await expect(page.getByTestId('archivos-cv-anterior')).toBeDisabled()
    await capturar(page, 'archivos-cv-listado')

    await page.getByTestId('archivos-cv-siguiente').click()
    await expect(page.getByTestId('archivos-cv-pagina')).toHaveText(`Página 2 de ${paginas}`)
    await expect(page.getByTestId('archivos-cv-rango')).toContainText('21')
    await page.getByTestId('archivos-cv-anterior').click()
    await expect(page.getByTestId('archivos-cv-pagina')).toHaveText(`Página 1 de ${paginas}`)

    // Búsqueda en el servidor (con espera de 300 ms) y vuelta a la página 1
    await page.getByTestId('archivos-cv-buscar').fill('e2e_param_07')
    await expect(page.getByTestId('archivos-cv-fila')).toHaveCount(1)
    await expect(page.getByTestId('archivos-cv-fila')).toContainText('e2e_param_07.pdf')
    await expect(page.getByTestId('archivos-cv-pagina')).toHaveText('Página 1 de 1')

    // Descarga real (solo lectura) por la ruta de Flask
    const descarga = page.waitForEvent('download')
    await page.getByTestId('archivos-cv-fila').getByTestId('archivos-cv-descargar').click()
    expect((await descarga).suggestedFilename()).toBe('e2e_param_07.pdf')
    await expect(aviso(page, 'Descargando «e2e_param_07.pdf» de cv_procesados_ok.')).toBeVisible()

    await page.getByTestId('archivos-cv-buscar').fill('zzz-no-existe')
    await expect(page.getByTestId('archivos-cv-tabla')).toContainText('Ningún archivo coincide con la búsqueda.')

    // Carpeta de errores: agrega la columna del motivo
    await page.getByTestId('archivos-cv-tarjeta-cv_errores').click()
    await expect(page.getByTestId('archivos-cv-carpeta-seleccionada')).toHaveText('cv_errores')
    await expect(page.getByTestId('archivos-cv-th-motivo')).toHaveText('Motivo del error')
    await expect(page.getByTestId('archivos-cv-descargar-todos')).toHaveAttribute('href', '/recruiting/parametros/archivos-cv/cv_errores/descargar-todos')
    await capturar(page, 'archivos-cv-errores')
  })

  test('backup (mock): progreso, resumen y enlace de descarga', async ({ page }) => {
    const cortadas = await mockearOperacionesDestructivas(page, importacion('finalizado'))
    await page.goto('/v2/recruiting/parametros/archivos-cv')
    await page.getByTestId('archivos-cv-backup').click()
    await expect(page.getByTestId('modal-backup')).toBeVisible()
    await page.getByTestId('backup-cancelar').click()
    await expect(page.getByTestId('modal-backup')).toHaveCount(0)
    await page.getByTestId('archivos-cv-backup').click()
    await page.getByTestId('backup-generar').click()
    await expect(page.getByTestId('backup-titulo')).toHaveText('Backup completado', { timeout: 15_000 })
    await expect(page.getByTestId('backup-resumen')).toContainText('recruiting-backup-e2e.zip')
    await expect(page.getByTestId('backup-descargar')).toHaveAttribute('href', `/recruiting/parametros/archivos-cv/backup/${BACKUP_ID}/descargar`)
    await expect(aviso(page, 'Backup de Recruiting completado.')).toBeVisible()
    await capturar(page, 'archivos-cv-backup')
    await page.getByTestId('backup-cerrar').click()
    expect(cortadas).toEqual([])
  })

  test('importación (mock): vista previa, cancelar descarta, confirmación con REEMPLAZAR y resultado con cuentas sin contraseña', async ({ page }) => {
    const cortadas = await mockearOperacionesDestructivas(
      page,
      importacion('finalizado', { resultado: { total_registros: 3, total_archivos: 2, archivos_storage: null, backup_seguridad: null, usuarios_sin_credenciales: [{ id: 'u1', email: 'restaurado@example.com' }] } }),
    )
    await page.goto('/v2/recruiting/parametros/archivos-cv')
    // Un archivo que no es .zip se rechaza sin subir nada
    await page.getByTestId('archivos-cv-importar-archivo').setInputFiles({ name: 'backup.txt', mimeType: 'text/plain', buffer: Buffer.from('x') })
    await expect(page.getByTestId('importar-error')).toContainText('Seleccioná un backup en formato .zip generado por RECLUIT.')
    await page.getByTestId('importar-cerrar').click()

    await page.getByTestId('archivos-cv-importar-archivo').setInputFiles(zipFicticio)
    await expect(page.getByTestId('importar-vista-previa')).toBeVisible()
    await expect(page.getByTestId('importar-integridad')).toContainText('SHA-256 verificado (mock)')
    await capturar(page, 'archivos-cv-importar-vista-previa')
    const descarte = page.waitForRequest((r) => r.method() === 'DELETE' && r.url().endsWith(`/importar/${IMPORTACION_ID}`))
    await page.getByTestId('importar-cancelar').click()
    await descarte
    await expect(page.getByTestId('modal-importar')).toHaveCount(0)

    await page.getByTestId('archivos-cv-importar-archivo').setInputFiles(zipFicticio)
    await page.getByTestId('importar-continuar').click()
    await expect(page.getByTestId('importar-confirmar')).toBeDisabled()
    await page.getByTestId('importar-texto-confirmacion').fill('reemplazar')
    await expect(page.getByTestId('importar-confirmar')).toBeDisabled()
    await page.getByTestId('importar-texto-confirmacion').fill('REEMPLAZAR')
    await page.getByTestId('importar-confirmar').click()
    await expect(page.getByTestId('importar-resultado')).toBeVisible({ timeout: 15_000 })
    await expect(page.getByTestId('importar-usuarios-sin-credenciales')).toContainText('restaurado@example.com')
    await capturar(page, 'archivos-cv-importar-resultado')
    // Con cuentas sin contraseña la página se recarga recién al cerrar
    const recarga = page.waitForEvent('load')
    await page.getByTestId('importar-cerrar').click()
    await recarga
    expect(cortadas).toEqual([])
  })

  test('importación (mock) con usuarios_sin_credenciales nulo (M11): resultado sin error y recarga automática', async ({ page }) => {
    const cortadas = await mockearOperacionesDestructivas(
      page,
      importacion('finalizado', { resultado: { total_registros: 3, total_archivos: 2, archivos_storage: null, backup_seguridad: null, usuarios_sin_credenciales: null } }),
    )
    await page.goto('/v2/recruiting/parametros/archivos-cv')
    await page.getByTestId('archivos-cv-importar-archivo').setInputFiles(zipFicticio)
    await page.getByTestId('importar-continuar').click()
    await page.getByTestId('importar-texto-confirmacion').fill('REEMPLAZAR')
    const recarga = page.waitForEvent('load', { timeout: 20_000 })
    await page.getByTestId('importar-confirmar').click()
    await expect(page.getByTestId('importar-resultado')).toBeVisible({ timeout: 15_000 })
    await expect(page.getByTestId('importar-usuarios-sin-credenciales')).toHaveCount(0)
    await recarga
    expect(cortadas).toEqual([])
  })

  test('limpieza (mock): cancelar no envía nada; confirmar va por la ruta de Flask (C1) y muestra el resumen', async ({ page, monitor }) => {
    const cortadas = await mockearOperacionesDestructivas(page, importacion('finalizado'))
    await page.goto('/v2/recruiting/parametros/archivos-cv')
    await page.getByTestId('archivos-cv-limpiar-bd').click()
    await expect(page.getByTestId('modal-limpiar-bd')).toContainText('Esta acción no se puede deshacer.')
    await page.getByTestId('limpiar-bd-cancelar').click()
    await expect(page.getByTestId('modal-limpiar-bd')).toHaveCount(0)
    expect(monitor.mutacionesDe(/limpiar-bd/)).toHaveLength(0)

    await page.getByTestId('archivos-cv-limpiar-bd').click()
    await page.getByTestId('limpiar-bd-confirmar').click()
    await expect(page.getByTestId('limpiar-bd-resumen')).toBeVisible()
    await expect(page.getByTestId('limpiar-bd-total-registros')).toHaveText('3')
    await expect(page.getByTestId('limpiar-bd-total-archivos')).toHaveText('2')
    await capturar(page, 'archivos-cv-limpieza-resumen')
    expect(monitor.mutacionesDe(/limpiar-bd/).map((m) => `${m.metodo} ${m.url}`)).toEqual(['POST /recruiting/parametros/archivos-cv/limpiar-bd'])
    await page.getByTestId('limpiar-bd-aceptar').click()
    await expect(page.getByTestId('modal-limpiar-bd')).toHaveCount(0)
    expect(cortadas).toEqual([])
  })

  test('limpieza (mock) rechazada: muestra el error del servidor', async ({ page, monitor }) => {
    monitor.permitir(/^403 POST \/recruiting\/parametros\/archivos-cv\/limpiar-bd$/)
    await mockearOperacionesDestructivas(page, importacion('finalizado'))
    await page.route('**/recruiting/parametros/archivos-cv/limpiar-bd', (r) =>
      r.fulfill({ status: 403, json: { success: false, error: 'No tenés permiso para limpiar los datos de Recruiting' } }),
    )
    await page.goto('/v2/recruiting/parametros/archivos-cv')
    await page.getByTestId('archivos-cv-limpiar-bd').click()
    await page.getByTestId('limpiar-bd-confirmar').click()
    await expect(page.getByTestId('limpiar-bd-error')).toHaveText('No tenés permiso para limpiar los datos de Recruiting')
  })
})

// =====================================================================================================================
// Historial de cargas de CV (administrador)
// =====================================================================================================================

test.describe('Historial de cargas de CV (administrador)', () => {
  test.use({ storageState: estadoDe('admin') })
  test.beforeAll(() => sembrarHistorial())

  test('listado, columnas, detalle y filtros', async ({ page }) => {
    await page.goto('/recruiting/parametros/historial-cargas-cv')
    await expect(page.getByTestId('historial-tabla').locator('thead th')).toHaveText([
      'Fecha y hora', 'Usuario', 'Tipo', 'Total', 'Creados', 'Duplicados', 'Sin email', 'Rechazados', 'Resultado', 'Acción',
    ])
    const filas = page.getByTestId('historial-fila')
    await expect(filas.first()).toBeVisible()
    const total = await filas.count()
    expect(total).toBeGreaterThanOrEqual(1)
    await capturar(page, 'historial-listado')

    await filas.first().getByTestId('historial-ver-detalle').click()
    await expect(page.getByTestId('historial-detalle')).toBeVisible()
    await expect(page.getByTestId('historial-detalle')).toContainText('Detalle de la carga')
    await expect(page.getByTestId('historial-detalle-fila').first()).toBeVisible()
    await capturar(page, 'historial-detalle')
    await page.getByTestId('historial-detalle-cerrar').click()
    await expect(page.getByTestId('historial-detalle')).toHaveCount(0)

    await page.getByTestId('historial-filtro-resultado').selectOption('completada')
    await page.getByTestId('historial-filtrar').click()
    await expect(filas.first()).toBeVisible()
    for (const r of await page.getByTestId('historial-resultado').allInnerTexts()) expect(r).toContain('Completada')

    await page.getByTestId('historial-filtro-usuario').fill('zzz-no-existe')
    await page.getByTestId('historial-filtrar').click()
    await expect(page.getByTestId('historial-vacio')).toBeVisible()
    await page.getByTestId('historial-limpiar').click()
    await expect(filas).toHaveCount(total)
  })
})

// =====================================================================================================================
// Usuario NO administrador con el ítem Parámetros
// =====================================================================================================================

test.describe('usuario con Parámetros que no es administrador', () => {
  test.beforeEach(async ({ page }) => {
    await ingresar(page, await usuarioParametros())
  })

  test('ve los catálogos y Archivos de CV sin las acciones de administrador ni la pestaña del historial', async ({ page }) => {
    sembrarArchivosCv()
    await page.goto('/recruiting/parametros/skills')
    await esperarTabla(page)
    const pestanas = page.getByTestId('parametros-pestanas').locator('a')
    await expect(pestanas).toHaveCount(10)
    await expect(pestanas.filter({ hasText: 'Historial de cargas de CV' })).toHaveCount(0)
    await page.goto('/recruiting/parametros/archivos-cv')
    await expect(page.getByTestId('archivos-cv-fila').first()).toBeVisible()
    for (const id of ['archivos-cv-backup', 'archivos-cv-importar', 'archivos-cv-limpiar-bd']) await expect(page.getByTestId(id)).toHaveCount(0)
    await capturar(page, 'no-admin-archivos-cv')
  })

  test('historial: 403 por la URL de siempre, por /v2, con barra final y por navegación interna (M1)', async ({ page, monitor }) => {
    monitor.permitir(/^403 GET \/(recruiting|v2\/recruiting)\/parametros\/historial-cargas-cv$/)
    for (const url of ['/recruiting/parametros/historial-cargas-cv', '/v2/recruiting/parametros/historial-cargas-cv', '/v2/recruiting/parametros/historial-cargas-cv/']) {
      const r = await page.goto(url)
      expect(r?.status(), url).toBe(403)
      await expect(page.getByTestId('historial-tabla'), url).toHaveCount(0)
    }
    await capturar(page, 'no-admin-historial-403')

    // Navegación interna de la SPA (sin pasar por Flask): termina en una carga completa con el 403 de Flask
    await page.goto('/v2/recruiting/parametros')
    const respuesta = page.waitForResponse((r) => r.url().endsWith('/v2/recruiting/parametros/historial-cargas-cv'))
    await page.evaluate(() => {
      const app = (document.querySelector('#app') as unknown as { __vue_app__: { config: { globalProperties: { $router: { push: (r: string) => Promise<unknown> } } } } }).__vue_app__
      void app.config.globalProperties.$router.push('/recruiting/parametros/historial-cargas-cv')
    })
    expect((await respuesta).status()).toBe(403)
  })

  test('historial: una variante en mayúsculas no abre la pantalla (Pantalla no encontrada) y la API responde 403', async ({ page, monitor }) => {
    monitor.permitir(/^403 GET \/api\/v1\/recruiting\/parametros\/historial-cargas-cv$/)
    await page.goto('/v2/recruiting/Parametros/historial-cargas-cv')
    await expect(page.getByText('Pantalla no encontrada')).toBeVisible()
    await expect(page.getByTestId('historial-tabla')).toHaveCount(0)
    const api = await page.request.get('/api/v1/recruiting/parametros/historial-cargas-cv')
    expect(api.status()).toBe(403)
  })

  test('las operaciones de administrador responden 403 (Flask y backend)', async ({ page, baseURL }) => {
    await page.goto('/v2/recruiting/parametros/archivos-cv')
    const limpiar = await page.request.post('/recruiting/parametros/archivos-cv/limpiar-bd', { headers: { Origin: baseURL!, Accept: 'application/json' } })
    expect(limpiar.status()).toBe(403)
    expect(await limpiar.json()).toEqual({ success: false, error: 'No tenés permiso para limpiar los datos de Recruiting' })
    const backup = await page.request.post('/api/v1/recruiting/parametros/archivos-cv/backup/iniciar', { headers: { Origin: baseURL! } })
    expect(backup.status()).toBe(403)
  })
})

// =====================================================================================================================
// Usuario sin el ítem Parámetros
// =====================================================================================================================

test.describe('usuario sin el ítem Parámetros', () => {
  test.use({ storageState: estadoDe('sinPermiso') })

  test('las 11 pantallas responden 403 por la URL de siempre y por /v2', async ({ page, monitor }) => {
    monitor.permitir(/^403 GET \/(recruiting|v2\/recruiting)\/parametros/)
    for (const p of PANTALLAS) {
      for (const url of [p.legacy, `/v2${p.legacy}`]) {
        const r = await page.goto(url)
        expect(r?.status(), url).toBe(403)
      }
    }
    await capturar(page, 'sin-permiso-403')
  })
})

test.afterAll(() => {
  writeFileSync(path.join(CAPTURAS, 'LEEME.txt'), `Capturas de la corrida ${SUFIJO} (stack E2E aislado).\n`)
})
