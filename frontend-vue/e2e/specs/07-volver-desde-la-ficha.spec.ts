import { estadoDe, expect, semilla, test } from '../fixtures'
import { FILAS, abrirGrilla, contarEnBase, esperarGrilla, totalMostrado } from '../helpers'

/**
 * «Volver» desde la ficha tras haber buscado en la grilla. Criterio legacy: el enlace «Ver candidato» de la grilla era
 * /recruiting/candidatos/<id> SIN `volver`, y «Volver» de la ficha usa volver_a(/recruiting/candidatos): vuelve al
 * listado sin filtros. El botón «Atrás» del navegador, en cambio, restaura la URL con la búsqueda.
 */
test.use({ storageState: estadoDe('autorizado') })

test('Volver desde la ficha lleva al listado completo (como el legacy: el enlace de la grilla no llevaba `volver`)', async ({ page }) => {
  const c = semilla().candidatos.completo!
  await abrirGrilla(page, '?busqueda=Camila')
  await expect(page.locator(FILAS)).toHaveCount(1)
  await page.getByTestId('accion-ver').first().click()
  await expect(page.getByTestId('detalle-nombre')).toHaveText('Camila Completa')
  expect(new URL(page.url()).searchParams.has('volver'), 'el enlace de la grilla no agrega `volver` (como el legacy)').toBe(false)
  await page.getByTestId('volver').click()
  await esperarGrilla(page)
  expect(new URL(page.url()).search).toBe('')
  // Coherencia entre lo que se ve y lo que se consulta: el buscador está vacío y el listado no está filtrado
  await expect(page.getByTestId('filtro-busqueda')).toHaveValue('')
  expect(await totalMostrado(page)).toBe(contarEnBase())
  void c
})

test('«Atrás» del navegador desde la ficha restaura la grilla con la búsqueda aplicada y su texto en el buscador', async ({ page }) => {
  await abrirGrilla(page, '?busqueda=Camila')
  await page.getByTestId('accion-ver').first().click()
  await expect(page.getByTestId('detalle-nombre')).toBeVisible()
  await page.goBack()
  await esperarGrilla(page)
  expect(new URL(page.url()).searchParams.get('busqueda')).toBe('Camila')
  await expect(page.getByTestId('filtro-busqueda')).toHaveValue('Camila')
  await expect(page.locator(FILAS)).toHaveCount(1)
  expect(await totalMostrado(page)).toBe(1)
})

test('con `volver` explícito (como desde «Ver Detalles»), Volver restaura la búsqueda en el buscador y en el resultado', async ({ page }) => {
  const id = semilla().candidatos.completo!.id
  await page.goto(`/recruiting/candidatos/${id}?volver=${encodeURIComponent('/recruiting/candidatos?page=1&limit=20&busqueda=Camila')}`)
  await expect(page.getByTestId('detalle-nombre')).toBeVisible()
  await page.getByTestId('volver').click()
  await esperarGrilla(page)
  await expect(page.getByTestId('filtro-busqueda')).toHaveValue('Camila')
  await expect(page.locator(FILAS)).toHaveCount(1)
})
