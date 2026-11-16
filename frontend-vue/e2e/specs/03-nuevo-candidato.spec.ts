import { estadoDe, expect, test } from '../fixtures'
import { crearPdf, textoCv } from '../archivos'
import { candidatoEnBase, esperarGrilla } from '../helpers'
import { sql } from '../stack'

/**
 * Nuevo Candidato. Criterio legacy (candidato_form.html): campos obligatorios Nombres, Apellido, Email y Teléfono; fecha
 * DD-MM-AAAA entre 1900 y 2010; teléfono solo dígitos y «+»; ciudad dependiente de la provincia; seniority inicial =
 * primer nivel; modalidad inicial «Remoto»; alta por POST /recruiting/candidatos; CV (PDF/DOC/DOCX hasta 2 MB) por
 * /recruiting/candidatos/<id>/cv; al guardar vuelve a la pantalla de origen.
 */
test.use({ storageState: estadoDe('autorizado') })

const abrir = async (page: import('@playwright/test').Page, query = '') => {
  await page.goto(`/recruiting/candidatos/nuevo${query}`)
  await expect(page.getByTestId('guardar')).toBeVisible()
  await expect(page.locator('#provincia')).toBeVisible()
}
const campo = (page: import('@playwright/test').Page, id: string) => page.locator(`#${id}`)
async function elegirEn(page: import('@playwright/test').Page, id: string, opcion: string) {
  await page.locator(`#${id}`).click()
  await page.getByRole('option', { name: opcion, exact: true }).click()
}

test.describe('apertura y catálogos', () => {
  test('se abre desde el botón «Nuevo Candidato» de la grilla', async ({ page }) => {
    await page.goto('/recruiting/candidatos')
    await esperarGrilla(page)
    await page.getByTestId('nuevo-candidato').click()
    await expect(page).toHaveURL(/\/v2\/recruiting\/candidatos\/nuevo/)
    await expect(page.getByRole('heading', { name: 'Nuevo Candidato' })).toBeVisible()
  })

  test('valores iniciales: campos vacíos, seniority = primer nivel y modalidad Remoto', async ({ page }) => {
    await abrir(page)
    for (const id of ['nombre', 'apellido', 'email', 'telefono', 'linkedin', 'dni', 'fecha-nacimiento']) await expect(campo(page, id), id).toHaveValue('')
    await expect(page.locator('#seniority')).toHaveText('Trainee')
    await expect(page.locator('#modalidad')).toHaveText('Remoto')
    await expect(page.locator('#provincia')).toContainText('Seleccionar provincia...')
    await expect(page.locator('#ciudad')).toContainText('Seleccionar ciudad...')
    await expect(page.locator('#puesto')).toContainText('Seleccionar puesto...')
    await expect(page.getByTestId('skills-elegidas')).toContainText('Ninguna tecnología seleccionada')
    await expect(page.getByTestId('habilidades-elegidas')).toContainText('Ninguna habilidad o competencia seleccionada')
  })

  test('catálogos reales: provincias, seniority, puestos, skills y competencias', async ({ page }) => {
    await abrir(page)
    await page.locator('#provincia').click()
    const provincias = await page.getByRole('option').allInnerTexts()
    expect(provincias.slice(0, 2)).toEqual(['Cordoba', 'Buenos Aires']) // orden de la pantalla anterior
    expect(provincias).toContain('Otros') // «No identificada» se muestra como «Otros»
    await page.keyboard.press('Escape')
    await expect(page.getByRole('listbox')).toHaveCount(0)
    await page.locator('#seniority').click()
    expect(await page.getByRole('option').allInnerTexts()).toEqual(['Trainee', 'Junior', 'Semi Senior', 'Senior'])
    await page.keyboard.press('Escape')
    await expect(page.getByRole('listbox')).toHaveCount(0)
    await page.locator('#puesto').click()
    const puestos = await page.getByRole('option').allInnerTexts()
    expect(puestos).toContain('Desarrollador Backend')
    expect(puestos.length).toBeGreaterThan(10)
    await page.keyboard.press('Escape')
    await expect(page.getByRole('listbox')).toHaveCount(0)
    const botonesSkills = page.getByTestId('skills-elegidas').locator('xpath=following-sibling::div[1]//button')
    expect(await botonesSkills.count()).toBeGreaterThan(20)
    const botonesHab = page.getByTestId('habilidades-elegidas').locator('xpath=following-sibling::div[1]//button')
    expect(await botonesHab.count()).toBeGreaterThan(5)
  })

  test('ciudad dependiente de la provincia: se habilita al elegir, lista las de esa provincia y se limpia al cambiar', async ({ page }) => {
    await abrir(page)
    await expect(page.locator('.p-select', { has: page.locator('#ciudad') })).toHaveClass(/p-disabled/)
    await elegirEn(page, 'provincia', 'Cordoba')
    await expect(page.locator('.p-select', { has: page.locator('#ciudad') })).not.toHaveClass(/p-disabled/)
    await page.locator('#ciudad').click()
    const ciudades = await page.getByRole('option').allInnerTexts()
    expect(ciudades).toContain('Cordoba Capital')
    await page.getByRole('option', { name: 'Cordoba Capital', exact: true }).click()
    await expect(page.locator('#ciudad')).toHaveText('Cordoba Capital')
    await elegirEn(page, 'provincia', 'Buenos Aires')
    await expect(page.locator('#ciudad')).toContainText('Seleccionar ciudad...')
    await page.locator('#ciudad').click()
    expect(await page.getByRole('option').allInnerTexts()).not.toContain('Cordoba Capital')
  })
})

test.describe('validaciones', () => {
  test('guardar vacío: avisa los 4 obligatorios y no envía nada al backend', async ({ page, monitor }) => {
    await abrir(page)
    await page.getByTestId('guardar').click()
    await expect(page.getByTestId('error-general')).toHaveText('Por favor completá los campos obligatorios (*): Nombre, Apellido, Email y Teléfono.')
    await expect(page.getByText('Ingresá los nombres')).toBeVisible()
    await expect(page.getByText('Ingresá el apellido')).toBeVisible()
    await expect(page.getByText('Ingresá el email', { exact: true })).toBeVisible()
    await expect(page.getByText('Ingresá el teléfono')).toBeVisible()
    expect(monitor.mutacionesDe(/POST \/api\/v1\/recruiting\/candidatos/)).toHaveLength(0)
  })

  test('email con formato inválido', async ({ page, monitor }) => {
    await abrir(page)
    await campo(page, 'nombre').fill('Test')
    await campo(page, 'apellido').fill('Email')
    await campo(page, 'telefono').fill('3515550000')
    for (const malo of ['sin-arroba', 'a@b', 'a@@b.com', 'a b@c.com']) {
      await campo(page, 'email').fill(malo)
      await page.getByTestId('guardar').click()
      await expect(page.getByText('Ingresá un email válido'), malo).toBeVisible()
    }
    expect(monitor.mutacionesDe(/POST \/api\/v1\/recruiting\/candidatos/)).toHaveLength(0)
  })

  test('teléfono: solo dígitos y «+»; fecha: máscara DD-MM-AAAA y rango 1900-2010', async ({ page }) => {
    await abrir(page)
    await campo(page, 'telefono').fill('+54 (351) 555-abc 0000')
    await expect(campo(page, 'telefono')).toHaveValue('+543515550000')
    await campo(page, 'fecha-nacimiento').fill('17051990')
    await expect(campo(page, 'fecha-nacimiento')).toHaveValue('17-05-1990')
    await expect(page.getByTestId('error-fecha')).toHaveCount(0)
    await campo(page, 'fecha-nacimiento').fill('31-02-1990')
    await expect(page.getByTestId('error-fecha')).toHaveText('Fecha inválida')
    await campo(page, 'fecha-nacimiento').fill('01-01-1899')
    await expect(page.getByTestId('error-fecha')).toHaveText('El año de nacimiento debe estar entre 1900 y 2010')
    await campo(page, 'fecha-nacimiento').fill('01-01-2011')
    await expect(page.getByTestId('error-fecha')).toHaveText('El año de nacimiento debe estar entre 1900 y 2010')
    await campo(page, 'fecha-nacimiento').fill('01-13-1990')
    await expect(page.getByTestId('error-fecha')).toHaveText('Fecha inválida')
  })

  test('una fecha inválida impide guardar aunque los obligatorios estén completos', async ({ page, monitor }) => {
    await abrir(page)
    await campo(page, 'nombre').fill('Fecha')
    await campo(page, 'apellido').fill('Mala')
    await campo(page, 'email').fill('fecha.mala@example.com')
    await campo(page, 'telefono').fill('3515550000')
    await campo(page, 'fecha-nacimiento').fill('01-01-2011')
    await page.getByTestId('guardar').click()
    await expect(page.getByTestId('error-general')).toContainText('El año de nacimiento debe estar entre 1900 y 2010')
    expect(monitor.mutacionesDe(/POST \/api\/v1\/recruiting\/candidatos/)).toHaveLength(0)
    expect(candidatoEnBase('fecha.mala@example.com')).toBeNull()
  })

  test('CV: solo PDF/DOC/DOCX y hasta 2 MB', async ({ page }) => {
    await abrir(page)
    await page.getByTestId('cv-input').setInputFiles({ name: 'cv.txt', mimeType: 'text/plain', buffer: Buffer.from('hola') })
    await expect(page.getByTestId('cv-error')).toContainText('Formato inválido. Solo se admiten archivos PDF, DOC o DOCX.')
    await page.getByTestId('cv-input').setInputFiles({ name: 'grande.pdf', mimeType: 'application/pdf', buffer: Buffer.alloc(2 * 1024 * 1024 + 10, 65) })
    await expect(page.getByTestId('cv-error')).toContainText('El archivo supera el tamaño máximo permitido de 2 MB.')
    await page.getByTestId('cv-input').setInputFiles({ name: 'ok.pdf', mimeType: 'application/pdf', buffer: crearPdf(['hola']) })
    await expect(page.getByTestId('cv-nombre')).toHaveText('ok.pdf')
    await expect(page.getByTestId('cv-error')).toHaveCount(0)
  })

  test('error del backend: se muestra su mensaje y no se crea el candidato', async ({ page, monitor }) => {
    monitor.permitir(/^422 POST \/api\/v1\/recruiting\/candidatos/)
    await abrir(page)
    await campo(page, 'nombre').fill('Backend')
    await campo(page, 'apellido').fill('Rechaza')
    await campo(page, 'email').fill('backend.rechaza@example.test') // formato válido para la pantalla; el backend lo rechaza
    await campo(page, 'telefono').fill('3515550000')
    await page.getByTestId('guardar').click()
    await expect(page.getByTestId('error-general')).toContainText('Email')
    expect(candidatoEnBase('backend.rechaza@example.test')).toBeNull()
    await expect(page).toHaveURL(/\/nuevo/)
  })
})

test.describe('alta de un candidato real en la base E2E', () => {
  const email = 'alta.completa.e2e@example.com'

  test('alta completa: datos enviados = datos ingresados, persisten en la base y se ven en grilla y ficha', async ({ page, monitor }) => {
    monitor.permitir(/^$/) // sin errores esperados
    await abrir(page, '?volver=/recruiting/candidatos?seniority=Senior')
    await campo(page, 'nombre').fill('Alta')
    await campo(page, 'apellido').fill('Completa')
    await campo(page, 'email').fill(email)
    await campo(page, 'telefono').fill('+5493515559999')
    await elegirEn(page, 'provincia', 'Cordoba')
    await elegirEn(page, 'ciudad', 'Cordoba Capital')
    await campo(page, 'linkedin').fill('https://linkedin.com/in/alta-completa')
    await campo(page, 'dni').fill('28999111')
    await campo(page, 'fecha-nacimiento').fill('17051990')
    await elegirEn(page, 'puesto', 'Desarrollador Backend')
    await elegirEn(page, 'seniority', 'Senior')
    await elegirEn(page, 'modalidad', 'Híbrido')
    const skills = page.getByTestId('skills-elegidas').locator('xpath=following-sibling::div[1]//button')
    const s1 = (await skills.nth(0).innerText()).trim()
    const s2 = (await skills.nth(1).innerText()).trim()
    await skills.nth(0).click()
    await skills.nth(1).click()
    await campo(page, 'skills').fill('Tecnologia Propia E2E')
    await campo(page, 'skills').press('Enter')
    await campo(page, 'habilidades').fill('Competencia Propia E2E')
    await campo(page, 'habilidades').press('Enter')
    await page.getByTestId('cv-input').setInputFiles({ name: 'cv-alta.pdf', mimeType: 'application/pdf', buffer: crearPdf(textoCv({ nombre: 'Alta', apellido: 'Completa', email })) })

    const peticion = page.waitForRequest((r) => r.method() === 'POST' && /\/api\/v1\/recruiting\/candidatos$/.test(r.url()))
    await page.getByTestId('guardar').click()
    const enviado = (await peticion).postDataJSON() as Record<string, unknown>

    expect(enviado).toMatchObject({
      nombre: 'Alta', apellido: 'Completa', email, telefono: '+5493515559999', dni: '28999111', fecha_nacimiento: '1990-05-17',
      linkedin_url: 'https://linkedin.com/in/alta-completa', headline: 'Desarrollador Backend', seniority: 'Senior', modalidad: 'Híbrido',
    })
    expect(enviado.skills).toEqual([s1, s2, 'Tecnologia Propia E2E'])
    expect(enviado.habilidades).toEqual(['Competencia Propia E2E'])
    expect(enviado.provincia_id).toBe(1)
    expect(typeof enviado.ciudad_id).toBe('number')

    await expect(page.getByText('Candidato guardado exitosamente.')).toBeVisible()
    // Navegación posterior: vuelve a la pantalla de origen (?volver=), que ya es Vue
    await expect(page).toHaveURL(/\/v2\/recruiting\/candidatos\?.*seniority=Senior/, { timeout: 15_000 })

    // Persistencia real en la base E2E
    const fila = sql(`select nombre, apellido, telefono, dni, fecha_nacimiento::text, provincia_id, ciudad_id, headline, seniority, modalidad, linkedin_url, fuente, estado, activo, cv_url is not null, skills::text, habilidades::text from recruiting_candidatos where lower(email)='${email}'`)[0]!
    expect(fila.slice(0, 15)).toEqual(['Alta', 'Completa', '+5493515559999', '28999111', '1990-05-17', '1', fila[6], 'Desarrollador Backend', 'Senior', 'Híbrido', 'https://linkedin.com/in/alta-completa', 'Portal Propio', 'Activo', 't', 't'])
    expect(fila[15]).toContain('Tecnologia Propia E2E')
    expect(fila[16]).toContain('Competencia Propia E2E')
    // un solo POST de alta (sin duplicados) y una sola fila
    expect(monitor.mutacionesDe(/POST \/api\/v1\/recruiting\/candidatos$/)).toHaveLength(1)
    expect(monitor.mutacionesDe(/POST \/recruiting\/candidatos\/[0-9a-f-]+\/cv/)).toHaveLength(1)
    expect(sql(`select count(*) from recruiting_candidatos where lower(email)='${email}'`)[0]![0]).toBe('1')

    // Después de recargar, el candidato está en la grilla y la ficha muestra lo ingresado
    await page.goto(`/recruiting/candidatos?busqueda=${email}`)
    await esperarGrilla(page)
    await expect(page.locator('.p-datatable-tbody > tr').first()).toContainText('Alta Completa')
    await page.getByTestId('accion-ver').first().click()
    await expect(page.getByTestId('detalle-nombre')).toHaveText('Alta Completa')
    await expect(page.getByTestId('detalle-salario')).toHaveText('-')
    await expect(page.getByTestId('detalle-skills')).toContainText('Tecnologia Propia E2E')
    await expect(page.getByTestId('descargar-cv')).toBeVisible()
  })

  test('alta solo con los obligatorios: valores por defecto y sin CV', async ({ page }) => {
    await abrir(page)
    await campo(page, 'nombre').fill('Minimo')
    await campo(page, 'apellido').fill('Obligatorios')
    await campo(page, 'email').fill('minimo.e2e@example.com')
    await campo(page, 'telefono').fill('3515551111')
    await page.getByTestId('guardar').click()
    await expect(page.getByText('Candidato guardado exitosamente.')).toBeVisible()
    await expect(page).toHaveURL(/\/v2\/recruiting\/candidatos$/, { timeout: 15_000 })
    const fila = candidatoEnBase('minimo.e2e@example.com', "nombre, seniority, modalidad, fuente, estado, cv_url is null, headline is null or headline=''")!
    expect(fila).toEqual(['Minimo', 'Trainee', 'Remoto', 'Portal Propio', 'Activo', 't', 't'])
  })

  test('doble clic en Guardar crea un solo candidato', async ({ page, monitor }) => {
    await abrir(page)
    await campo(page, 'nombre').fill('Doble')
    await campo(page, 'apellido').fill('Clic')
    await campo(page, 'email').fill('doble.clic.e2e@example.com')
    await campo(page, 'telefono').fill('3515552222')
    await page.getByTestId('guardar').dblclick()
    await expect(page.getByText('Candidato guardado exitosamente.')).toBeVisible()
    await expect(page).toHaveURL(/\/v2\/recruiting\/candidatos/, { timeout: 15_000 })
    expect(monitor.mutacionesDe(/POST \/api\/v1\/recruiting\/candidatos$/)).toHaveLength(1)
    expect(sql("select count(*) from recruiting_candidatos where lower(email)='doble.clic.e2e@example.com'")[0]![0]).toBe('1')
  })
})

test.describe('navegación', () => {
  test('Cancelar y Volver llevan a la pantalla de origen; sin «volver» van al listado', async ({ page }) => {
    await abrir(page)
    await page.getByTestId('cancelar').click()
    await expect(page).toHaveURL(/\/v2\/recruiting\/candidatos$/)
    await abrir(page, '?volver=/recruiting/candidatos?page=2%26limit=50')
    await page.getByTestId('volver').click()
    await expect(page).toHaveURL(/\/v2\/recruiting\/candidatos\?page=2&limit=50/)
    // «volver» ajeno a Recruiting se ignora (como la pantalla anterior)
    await abrir(page, '?volver=https://sitio-externo.example')
    await page.getByTestId('cancelar').click()
    await expect(page).toHaveURL(/\/v2\/recruiting\/candidatos$/)
  })
})
