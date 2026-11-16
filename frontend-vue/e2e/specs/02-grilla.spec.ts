import { estadoDe, expect, semilla, test } from '../fixtures'
import { FILAS, abrirGrilla, contarEnBase, elegir, esperarGrilla, etiquetaCombo, filaDe, proximaConsulta, textoIndicador, totalMostrado } from '../helpers'

/**
 * Grilla de Candidatos. Criterio legacy (candidatos.html + GET /recruiting/candidatos): paginación y filtros contra el
 * backend, parámetros en la URL (page, limit, busqueda, seniority, ubicacion, puesto, categorias, skills), combos con
 * sus textos iniciales y «Limpiar Filtros» que vuelve a ellos.
 */
test.use({ storageState: estadoDe('autorizado') })

const INICIALES = {
  'filtro-seniority': 'Todos los seniorities',
  'filtro-ubicacion': 'Todas las ubicaciones',
  'filtro-puesto': 'Todos los perfiles de puesto',
  'filtro-categoria': 'Todas las categorías',
  'filtro-skill': 'Todas las skills de la categoría',
}

test.describe('carga inicial', () => {
  test('muestra las 7 columnas, 20 filas y los indicadores de paginación', async ({ page }) => {
    await abrirGrilla(page)
    await expect(page.locator('.p-datatable-thead th')).toHaveText(['Candidato', 'Contacto / Email', 'Ubicación', 'Skills', 'Origen / Fuente', 'Estado', 'Acciones'], { ignoreCase: true })
    await expect(page.locator(FILAS)).toHaveCount(20)
    const total = contarEnBase()
    expect(await totalMostrado(page)).toBe(total)
    expect(await textoIndicador(page)).toContain(`Mostrando 1 a 20 de ${total} candidatos`)
    await expect(page.getByTestId('indicador-pagina')).toHaveText(`Página 1 de ${Math.ceil(total / 20)}`)
    await expect(page.getByTestId('selector-limite')).toContainText('20')
  })

  test('los datos de una fila coinciden con lo cargado en la base', async ({ page }) => {
    const c = semilla().candidatos.completo!
    await abrirGrilla(page, `?busqueda=${encodeURIComponent(c.email)}`)
    const fila = filaDe(page, c.apellido)
    await expect(fila).toHaveCount(1)
    await expect(fila).toContainText('Camila Completa')
    await expect(fila).toContainText(c.email)
    await expect(fila).toContainText('Tel: +5493515550101')
    await expect(fila).toContainText('LinkedIn')
    await expect(fila).toContainText('Activo')
    await expect(fila).toContainText('Cordoba')
    // 5 skills: se ven 2 y «+3» con el resto en el tooltip
    await expect(fila.getByTestId('skills-ocultas')).toHaveText('+3')
  })

  test('valores vacíos: sin skills, fuente por defecto y sin teléfono', async ({ page }) => {
    const c = semilla().candidatos.vacio!
    await abrirGrilla(page, `?busqueda=${encodeURIComponent(c.email)}`)
    const fila = filaDe(page, c.apellido)
    await expect(fila).toContainText('Sin skills registradas')
    await expect(fila).toContainText('Portal Propio')
    await expect(fila).not.toContainText('Tel:')
    await expect(fila.getByTitle('Descargar CV')).toHaveCount(0)
  })

  test('estados: Rechazado y Sin respuesta se muestran con su texto', async ({ page }) => {
    await abrirGrilla(page, `?busqueda=${encodeURIComponent('Rolando')}`)
    await expect(filaDe(page, 'Rechazado').first()).toBeVisible()
    await abrirGrilla(page, `?busqueda=${encodeURIComponent('Silencio')}`)
    await expect(filaDe(page, 'Sin respuesta').first()).toBeVisible()
  })
})

test.describe('valores iniciales de los combos y «Limpiar Filtros»', () => {
  test('con la URL sin parámetros los 5 combos muestran su texto inicial y la URL no cambia', async ({ page }) => {
    await abrirGrilla(page)
    for (const [id, texto] of Object.entries(INICIALES)) await expect(etiquetaCombo(page, id), id).toHaveText(texto)
    await expect(page.getByTestId('filtro-busqueda')).toHaveValue('')
    await expect(page.getByTestId('filtro-skill')).toHaveClass(/p-disabled/)
    expect(new URL(page.url()).search).toBe('')
  })

  test('Limpiar Filtros devuelve los valores iniciales, vacía la búsqueda y deja la URL en page/limit', async ({ page }) => {
    await abrirGrilla(page)
    await elegir(page, 'filtro-seniority', 'Senior')
    await elegir(page, 'filtro-ubicacion', 'Cordoba')
    await elegir(page, 'filtro-puesto', 'Desarrollador Backend')
    await page.getByTestId('filtro-busqueda').fill('Acosta')
    await page.getByTestId('filtro-busqueda').press('Enter')
    await esperarGrilla(page)
    await page.getByTestId('limpiar-filtros').click()
    await esperarGrilla(page)
    for (const [id, texto] of Object.entries(INICIALES)) await expect(etiquetaCombo(page, id), id).toHaveText(texto)
    await expect(page.getByTestId('filtro-busqueda')).toHaveValue('')
    expect(new URL(page.url()).search).toBe('?page=1&limit=20')
    expect(await totalMostrado(page)).toBe(contarEnBase())
  })

  test('Limpiar Filtros conserva el tamaño de página elegido', async ({ page }) => {
    await abrirGrilla(page, '?page=1&limit=50&seniority=Senior')
    await page.getByTestId('limpiar-filtros').click()
    await esperarGrilla(page)
    expect(new URL(page.url()).search).toBe('?page=1&limit=50')
  })
})

test.describe('filtros: realmente consultan al backend', () => {
  test('seniority: la consulta lleva el parámetro, el total coincide con la base y todas las filas son de ese nivel', async ({ page }) => {
    await abrirGrilla(page)
    const consulta = proximaConsulta(page)
    await elegir(page, 'filtro-seniority', 'Senior')
    expect((await consulta).get('seniority')).toBe('Senior')
    await esperarGrilla(page)
    await expect.poll(() => totalMostrado(page)).toBe(contarEnBase("seniority='Senior'"))
    await expect(etiquetaCombo(page, 'filtro-seniority')).toHaveText('Senior')
    expect(new URL(page.url()).searchParams.get('seniority')).toBe('Senior')
  })

  test('perfil de puesto: total igual a la base', async ({ page }) => {
    await abrirGrilla(page)
    await elegir(page, 'filtro-puesto', 'QA Tester / Automation')
    await expect.poll(() => totalMostrado(page)).toBe(contarEnBase("headline='QA Tester / Automation'"))
    expect(new URL(page.url()).searchParams.get('puesto')).toBe('QA Tester / Automation')
  })

  test('ubicación: Cordoba y Buenos Aires filtran en el backend; «Otros» trae el resto', async ({ page }) => {
    await abrirGrilla(page)
    const total = await totalMostrado(page)
    await elegir(page, 'filtro-ubicacion', 'Cordoba')
    await expect.poll(() => totalMostrado(page)).toBeLessThan(total)
    const cordoba = await totalMostrado(page)
    expect(cordoba, 'total de Cordoba = candidatos con provincia 1 en la base').toBe(contarEnBase('provincia_id=1'))
    await expect(page.locator(FILAS).first()).toContainText('Cordoba')
    await elegir(page, 'filtro-ubicacion', 'Buenos Aires')
    await expect(page.locator(FILAS).first()).toContainText('Buenos Aires')
    await expect.poll(() => totalMostrado(page)).toBe(contarEnBase('provincia_id=2'))
    await elegir(page, 'filtro-ubicacion', 'Otros')
    await expect.poll(() => new URL(page.url()).searchParams.get('ubicacion')).toBe('otros')
    await esperarGrilla(page)
    expect(await totalMostrado(page)).toBeGreaterThan(0)
  })

  test('búsqueda por texto: se aplica con Enter (no al escribir) y filtra por nombre/email', async ({ page }) => {
    await abrirGrilla(page)
    const antes = await totalMostrado(page)
    await page.getByTestId('filtro-busqueda').fill('Camila')
    await page.waitForTimeout(600)
    expect(await totalMostrado(page), 'escribir sin Enter no filtra').toBe(antes)
    const consulta = proximaConsulta(page)
    await page.getByTestId('filtro-busqueda').press('Enter')
    expect((await consulta).get('busqueda')).toBe('Camila')
    await expect(page.locator(FILAS)).toHaveCount(1)
    await expect(page.locator(FILAS).first()).toContainText('Camila Completa')
    // por email
    await page.getByTestId('filtro-busqueda').fill('elisa.elegible@example.com')
    await page.getByTestId('filtro-busqueda').press('Enter')
    await expect(page.locator(FILAS)).toHaveCount(1)
    await expect(page.locator(FILAS).first()).toContainText('Elisa Elegible')
  })

  test('búsqueda sin coincidencias: estado vacío y «Sin candidatos para mostrar»', async ({ page }) => {
    await abrirGrilla(page, '?busqueda=zzzinexistentezzz')
    await expect(page.getByTestId('sin-candidatos')).toContainText('No se encontraron candidatos en la base de talentos')
    expect(await textoIndicador(page)).toBe('Sin candidatos para mostrar')
    await expect(page.getByTestId('indicador-pagina')).toHaveText('Página 1 de 1')
    await expect(page.getByTestId('pagina-anterior')).toBeDisabled()
    await expect(page.getByTestId('pagina-siguiente')).toBeDisabled()
  })

  test('categoría y skills de la categoría: habilita el combo de skills, filtra y se reinicia al cambiar de categoría', async ({ page }) => {
    await abrirGrilla(page)
    await page.getByTestId('filtro-categoria').click()
    const categorias = await page.getByRole('option').allInnerTexts()
    expect(categorias.length).toBeGreaterThan(2)
    const categoria = categorias.find((c) => c !== 'Todas las categorías')!
    await page.getByRole('option', { name: categoria, exact: true }).click()
    await esperarGrilla(page)
    await expect(page.getByTestId('filtro-skill')).not.toHaveClass(/p-disabled/)
    expect(new URL(page.url()).searchParams.get('categorias')).toBe(categoria)
    const porCategoria = await totalMostrado(page)
    expect(porCategoria).toBeGreaterThan(0)
    expect(porCategoria).toBeLessThan(contarEnBase())

    await page.getByTestId('filtro-skill').click()
    const skills = (await page.getByRole('option').allInnerTexts()).filter((s) => s !== 'Todas las skills de la categoría')
    expect(skills.length).toBeGreaterThan(0)
    await page.getByRole('option', { name: skills[0]!, exact: true }).click()
    await esperarGrilla(page)
    expect(new URL(page.url()).searchParams.get('skills')).toBe(skills[0])
    expect(await totalMostrado(page)).toBeLessThanOrEqual(porCategoria)

    await elegir(page, 'filtro-categoria', 'Todas las categorías')
    await esperarGrilla(page)
    await expect(etiquetaCombo(page, 'filtro-skill')).toHaveText('Todas las skills de la categoría')
    expect(new URL(page.url()).searchParams.has('skills')).toBe(false)
    expect(new URL(page.url()).searchParams.has('categorias')).toBe(false)
  })

  test('combinación de filtros: la consulta los lleva todos y el resultado es la intersección', async ({ page }) => {
    await abrirGrilla(page)
    await elegir(page, 'filtro-seniority', 'Senior')
    await elegir(page, 'filtro-puesto', 'Desarrollador Backend')
    await esperarGrilla(page)
    const consulta = proximaConsulta(page)
    await page.getByTestId('filtro-busqueda').fill('Acosta')
    await page.getByTestId('filtro-busqueda').press('Enter')
    const p = await consulta
    expect([p.get('seniority'), p.get('puesto'), p.get('busqueda')]).toEqual(['Senior', 'Desarrollador Backend', 'Acosta'])
    await esperarGrilla(page)
    const esperado = contarEnBase("seniority='Senior' and headline='Desarrollador Backend' and (apellido ilike '%Acosta%' or nombre ilike '%Acosta%' or email ilike '%Acosta%')")
    await expect.poll(() => totalMostrado(page)).toBe(esperado)
  })
})

test.describe('URL, recarga e historial', () => {
  test('los filtros viven en la URL: se conservan al recargar', async ({ page }) => {
    await abrirGrilla(page, '?page=1&limit=20&seniority=Senior&puesto=Desarrollador%20Backend&busqueda=a')
    const total = await totalMostrado(page)
    await page.reload()
    await esperarGrilla(page)
    await expect(etiquetaCombo(page, 'filtro-seniority')).toHaveText('Senior')
    await expect(etiquetaCombo(page, 'filtro-puesto')).toHaveText('Desarrollador Backend')
    await expect(page.getByTestId('filtro-busqueda')).toHaveValue('a')
    expect(await totalMostrado(page)).toBe(total)
  })

  test('la URL original conserva los parámetros al redirigir a Vue (incluidos los alias legacy)', async ({ page }) => {
    await page.goto('/recruiting/candidatos?page=2&limit=50&seniority=Junior&ubicacion=otros')
    await esperarGrilla(page)
    const u = new URL(page.url())
    expect(u.pathname).toBe('/v2/recruiting/candidatos')
    expect([u.searchParams.get('page'), u.searchParams.get('limit'), u.searchParams.get('seniority'), u.searchParams.get('ubicacion')]).toEqual(['2', '50', 'Junior', 'otros'])
    await expect(etiquetaCombo(page, 'filtro-seniority')).toHaveText('Junior')
    await expect(etiquetaCombo(page, 'filtro-ubicacion')).toHaveText('Otros')
  })

  test('Atrás y Adelante del navegador restauran filtros y página', async ({ page }) => {
    await abrirGrilla(page)
    await elegir(page, 'filtro-seniority', 'Senior')
    await esperarGrilla(page)
    const conFiltro = await totalMostrado(page)
    await page.getByTestId('pagina-siguiente').click()
    await expect(page.getByTestId('indicador-pagina')).toContainText('Página 2')
    await page.goBack()
    await expect(page.getByTestId('indicador-pagina')).toContainText('Página 1')
    expect(await totalMostrado(page)).toBe(conFiltro)
    await page.goBack()
    await esperarGrilla(page)
    await expect(etiquetaCombo(page, 'filtro-seniority')).toHaveText('Todos los seniorities')
    await page.goForward()
    await expect(etiquetaCombo(page, 'filtro-seniority')).toHaveText('Senior')
    await page.goForward()
    await expect(page.getByTestId('indicador-pagina')).toContainText('Página 2')
  })
})

test.describe('paginación real del servidor', () => {
  test('cada página trae filas distintas del backend y el rango del indicador es correcto', async ({ page }) => {
    await abrirGrilla(page)
    const total = contarEnBase()
    const primera = await page.locator(FILAS).first().innerText()
    const consulta = proximaConsulta(page)
    await page.getByTestId('pagina-siguiente').click()
    const p = await consulta
    expect([p.get('pagina'), p.get('por_pagina')]).toEqual(['2', '20'])
    await expect(page.getByTestId('indicador-pagina')).toContainText('Página 2')
    expect(await textoIndicador(page)).toContain('Mostrando 21 a 40')
    expect(await page.locator(FILAS).first().innerText()).not.toBe(primera)
    await expect(page.getByTestId('pagina-anterior')).toBeEnabled()
    // última página: resto de filas y «Siguiente» deshabilitado
    const ultima = Math.ceil(total / 20)
    await abrirGrilla(page, `?page=${ultima}&limit=20`)
    await expect(page.locator(FILAS)).toHaveCount(total - (ultima - 1) * 20)
    await expect(page.getByTestId('pagina-siguiente')).toBeDisabled()
    expect(await textoIndicador(page)).toContain(`${(ultima - 1) * 20 + 1} a ${total} de ${total}`)
  })

  for (const limite of [20, 50, 100]) {
    test(`tamaño de página ${limite}: filas, páginas y parámetro por_pagina`, async ({ page }) => {
      await abrirGrilla(page)
      const total = contarEnBase()
      if (limite !== 20) {
        const consulta = proximaConsulta(page)
        await elegir(page, 'selector-limite', String(limite))
        expect((await consulta).get('por_pagina')).toBe(String(limite))
      }
      await esperarGrilla(page)
      await expect(page.locator(FILAS)).toHaveCount(Math.min(limite, total))
      await expect(page.getByTestId('indicador-pagina')).toHaveText(`Página 1 de ${Math.ceil(total / limite)}`)
      // Con el tamaño por defecto (20) la URL no lleva `limit`; con otro, sí.
      expect(new URL(page.url()).searchParams.get('limit')).toBe(limite === 20 ? null : String(limite))
    })
  }

  test('cambiar el tamaño de página vuelve a la primera página', async ({ page }) => {
    await abrirGrilla(page, '?page=3&limit=20')
    await elegir(page, 'selector-limite', '50')
    await esperarGrilla(page)
    expect(new URL(page.url()).searchParams.get('page')).toBe('1')
  })

  test('un tamaño inválido en la URL se acota a 20/50/100', async ({ page }) => {
    await abrirGrilla(page, '?limit=5000')
    await expect(page.getByTestId('selector-limite')).toContainText('100')
  })
})
