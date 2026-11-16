import type { Page, Request } from '@playwright/test'

import { expect } from './fixtures'
import { sql } from './stack'

/** Utilidades compartidas de las pruebas de Candidatos. */

export const FILAS = '.p-datatable-tbody > tr:not(.p-datatable-empty-message)'

export async function abrirGrilla(page: Page, query = ''): Promise<void> {
  await page.goto(`/recruiting/candidatos${query}`)
  await esperarGrilla(page)
}

/** Espera a que la grilla haya cargado (indicador visible y sin la carga en curso). */
export async function esperarGrilla(page: Page): Promise<void> {
  await expect(page.getByTestId('indicador-registros')).toBeVisible()
  await expect(page.locator('.p-datatable-mask')).toHaveCount(0)
}

/** Elige una opción de un combo de PrimeVue (por su data-testid) y espera a que se actualice la grilla. */
export async function elegir(page: Page, testid: string, opcion: string): Promise<void> {
  await page.getByTestId(testid).click()
  await page.getByRole('option', { name: opcion, exact: true }).click()
}

export const etiquetaCombo = (page: Page, testid: string) => page.getByTestId(testid).locator('.p-select-label')

export async function textoIndicador(page: Page): Promise<string> {
  return ((await page.getByTestId('indicador-registros').innerText()) || '').replace(/\s+/g, ' ').trim()
}

/** Total de la grilla según el indicador «Mostrando X a Y de Z candidatos». */
export async function totalMostrado(page: Page): Promise<number> {
  const m = /de (\d+) candidatos/.exec(await textoIndicador(page))
  return m ? Number(m[1]) : 0
}

/** Espera la próxima consulta del listado al backend y devuelve sus parámetros. */
export function proximaConsulta(page: Page): Promise<URLSearchParams> {
  return page
    .waitForRequest((r: Request) => /\/api\/v1\/recruiting\/candidatos\?/.test(r.url()))
    .then((r) => new URL(r.url()).searchParams)
}

/** Cantidad de candidatos activos (no dados de baja) en la base E2E que cumplen la condición SQL. */
export function contarEnBase(condicion = 'true'): number {
  const [fila] = sql(`select count(*) from recruiting_candidatos where activo and deleted_at is null and (${condicion})`)
  return Number(fila?.[0])
}

export function filaDe(page: Page, texto: string) {
  return page.locator('.p-datatable-tbody > tr', { hasText: texto })
}

/** Candidato en la base por email (null si no existe): columnas elegidas. */
export function candidatoEnBase(email: string, columnas = 'id, nombre, apellido, activo, deleted_at is not null as borrado, cv_url'): string[] | null {
  const [fila] = sql(`select ${columnas} from recruiting_candidatos where lower(email)='${email.toLowerCase()}'`)
  return fila ?? null
}
