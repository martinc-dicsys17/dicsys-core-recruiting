// Pruebas de las reglas puras de la grilla de Candidatos (filtros, paginación, carga de CV), sin navegador.
// Ejecutar desde frontend-vue/:  node --test tests/candidatos_listado.test.mjs
import assert from 'node:assert/strict'
import test from 'node:test'

import { agruparPorCategoria } from '../src/modules/recruiting/candidatos/catalogos.ts'
import {
  agregarArchivosMasivo,
  categoriasResumen,
  detalleMatch,
  detalleNoCreados,
  errorArchivoIndividual,
  mensajeCancelado,
  mensajeEmailExistente,
  porcentajeLote,
  textoProgreso,
  tituloProgreso,
} from '../src/modules/recruiting/candidatos/cv.ts'
import {
  dividirSkills,
  estadoParaMostrar,
  filtrosDesdeQuery,
  filtrosVacios,
  normalizarLimite,
  parametrosApi,
  queryDesdeFiltros,
  rangoRegistros,
  urlDeVuelta,
} from '../src/modules/recruiting/candidatos/filtros.ts'

const archivo = (name, size = 1000) => ({ name, size })

// ---- Filtros y URL ----

test('sin parámetros: página 1, 20 por página y sin filtros', () => {
  assert.deepEqual(filtrosDesdeQuery({}), filtrosVacios())
})

test('lee todos los filtros de la URL, con los alias de la pantalla anterior', () => {
  const f = filtrosDesdeQuery({
    q: 'ana',
    seniority: 'Senior',
    ubicacion: 'otros',
    puesto: 'QA Tester',
    categorias: 'Lenguajes',
    skills: 'Python',
    estado: 'Activo',
    fuente: 'LinkedIn',
    pagina: '3',
    por_pagina: '50',
  })
  assert.deepEqual(f, {
    busqueda: 'ana', seniority: 'Senior', ubicacion: 'otros', puesto: 'QA Tester', categoria: 'Lenguajes',
    skill: 'Python', estado: 'Activo', fuente: 'LinkedIn', pagina: 3, limite: 50,
  })
  assert.equal(filtrosDesdeQuery({ busqueda: 'x', search: 'y' }).busqueda, 'x')
})

test('con un parámetro repetido se toma el primero y se normalizan los espacios', () => {
  assert.equal(filtrosDesdeQuery({ categorias: ['Lenguajes', 'Bases'] }).categoria, 'Lenguajes')
  assert.equal(filtrosDesdeQuery({ busqueda: '  ana   perez ' }).busqueda, 'ana perez')
})

test('página inválida o menor a 1 vuelve a la primera', () => {
  assert.equal(filtrosDesdeQuery({ page: '0' }).pagina, 1)
  assert.equal(filtrosDesdeQuery({ page: '-4' }).pagina, 1)
  assert.equal(filtrosDesdeQuery({ page: 'abc' }).pagina, 1)
})

test('el tamaño de página se acota a 20, 50 o 100', () => {
  assert.deepEqual([5, 20, 21, 50, 51, 5000, null].map(normalizarLimite), [20, 20, 50, 50, 100, 100, 20])
  assert.equal(filtrosDesdeQuery({ limit: '5000' }).limite, 100)
})

test('la query de la URL lleva page y limit siempre y los filtros solo si tienen valor', () => {
  assert.deepEqual(queryDesdeFiltros(filtrosVacios(50)), { page: '1', limit: '50' })
  const f = { ...filtrosVacios(), busqueda: 'ana', categoria: 'Lenguajes', skill: 'Python', pagina: 2 }
  assert.deepEqual(queryDesdeFiltros(f), { page: '2', limit: '20', busqueda: 'ana', categorias: 'Lenguajes', skills: 'Python' })
})

test('la skill sin categoría no viaja en la URL', () => {
  assert.equal('skills' in queryDesdeFiltros({ ...filtrosVacios(), skill: 'Python' }), false)
})

test('la URL se puede ir y volver sin perder filtros', () => {
  const f = { ...filtrosVacios(100), seniority: 'Junior', ubicacion: 'Cordoba', puesto: 'QA', pagina: 4 }
  assert.deepEqual(filtrosDesdeQuery(queryDesdeFiltros(f)), f)
})

test('parámetros del backend: paginación, filtros, categoría y skill de esa categoría', () => {
  const f = { ...filtrosVacios(50), busqueda: 'ana perez', seniority: 'Senior', ubicacion: 'Cordoba', puesto: 'QA Tester', categoria: 'Lenguajes', skill: 'Python', pagina: 2 }
  const p = parametrosApi(f, ['Python', 'Java'])
  assert.deepEqual(Object.fromEntries(p), {
    pagina: '2', por_pagina: '50', busqueda: 'ana perez', seniority: 'Senior', ubicacion: 'Cordoba',
    puesto: 'QA Tester', categorias: 'Lenguajes', skills: 'Python',
  })
})

test('la skill que no es de la categoría elegida no se envía', () => {
  const p = parametrosApi({ ...filtrosVacios(), categoria: 'Lenguajes', skill: 'Photoshop' }, ['Python'])
  assert.equal(p.has('skills'), false)
  assert.equal(p.get('categorias'), 'Lenguajes')
})

test('sin filtros solo se envían página y tamaño', () => {
  assert.equal(parametrosApi(filtrosVacios(), []).toString(), 'pagina=1&por_pagina=20')
})

test('estado y fuente de la URL se reenvían al backend aunque no tengan selector', () => {
  const p = parametrosApi({ ...filtrosVacios(), estado: 'Inactivo', fuente: 'LinkedIn' }, [])
  assert.equal(p.get('estado'), 'Inactivo')
  assert.equal(p.get('fuente'), 'LinkedIn')
})

test('el destino de vuelta es la ruta de Flask con los filtros y la página', () => {
  const url = urlDeVuelta({ ...filtrosVacios(), busqueda: 'ana', pagina: 3 })
  assert.equal(url, '/recruiting/candidatos?page=3&limit=20&busqueda=ana')
})

// ---- Paginación y presentación ----

test('rango de registros mostrado', () => {
  assert.deepEqual(rangoRegistros(1, 20, 41), { desde: 1, hasta: 20 })
  assert.deepEqual(rangoRegistros(3, 20, 41), { desde: 41, hasta: 41 })
  assert.deepEqual(rangoRegistros(2, 50, 75), { desde: 51, hasta: 75 })
  assert.deepEqual(rangoRegistros(1, 20, 0), { desde: 0, hasta: 0 })
})

test('skills: dos visibles y el resto en el tooltip', () => {
  assert.deepEqual(dividirSkills(['a', 'b', 'c', 'd']), { visibles: ['a', 'b'], ocultas: ['c', 'd'] })
  assert.deepEqual(dividirSkills(['a']), { visibles: ['a'], ocultas: [] })
})

test('estado: dado de baja, activo y los demás', () => {
  assert.equal(estadoParaMostrar('Activo', false).texto, 'Dado de baja')
  assert.equal(estadoParaMostrar(undefined, true).texto, 'Activo')
  assert.match(estadoParaMostrar('Rechazado', true).clases, /red/)
  assert.match(estadoParaMostrar('Baja del proceso', true).clases, /dark/)
  assert.match(estadoParaMostrar('En proceso', true).clases, /amber/)
})

// ---- Catálogos de los filtros ----

test('categorías de skills: se unen las que difieren en mayúsculas o espacios y se ordenan', () => {
  const r = agruparPorCategoria([
    { nombre: 'Python', categoria: 'Lenguajes' },
    { nombre: 'Java ', categoria: 'lenguajes' },
    { nombre: 'Python', categoria: ' Lenguajes ' },
    { nombre: 'Docker', categoria: 'Herramientas' },
    { nombre: 'Sin categoria', categoria: null },
  ])
  assert.deepEqual(r.categorias, ['Herramientas', 'Lenguajes'])
  assert.deepEqual(r.skillsPorCategoria, { Lenguajes: ['Java', 'Python'], Herramientas: ['Docker'] })
})

// ---- Carga individual de CV ----

test('carga individual: formato y tamaño (hasta 5 MB)', () => {
  assert.equal(errorArchivoIndividual(archivo('cv.pdf')), null)
  assert.equal(errorArchivoIndividual(archivo('cv.DOCX')), null)
  assert.match(errorArchivoIndividual(archivo('cv.txt')), /Formato no admitido/)
  assert.match(errorArchivoIndividual(archivo('cv')), /Formato no admitido/)
  assert.match(errorArchivoIndividual(archivo('cv.pdf', 5 * 1024 * 1024 + 1)), /5 MB/)
  assert.equal(errorArchivoIndividual(archivo('cv.pdf', 5 * 1024 * 1024)), null)
})

test('email ya registrado: se informa con el email', () => {
  assert.equal(
    mensajeEmailExistente('Ya existe un candidato registrado con este email: ana@example.com', 400),
    'El candidato ya se encuentra registrado con el email ana@example.com.',
  )
  assert.equal(mensajeEmailExistente('otro', 409), 'El candidato ya se encuentra registrado con este email.')
  assert.equal(mensajeEmailExistente('Error al procesar', 422), null)
})

// ---- Carga masiva ----

test('carga masiva: acepta PDF, DOC, DOCX, ZIP y RAR y rechaza el resto sin perder lo demás', () => {
  const r = agregarArchivosMasivo([], [archivo('a.pdf'), archivo('b.zip'), archivo('c.exe')])
  assert.deepEqual(r.archivos.map((f) => f.name), ['a.pdf', 'b.zip'])
  assert.match(r.errores, /Formato no admitido: "c.exe"/)
  assert.equal(r.advertenciaLimite, '')
})

test('carga masiva: el límite de 100 CVs individuales rechaza la selección nueva y conserva la anterior', () => {
  const actuales = Array.from({ length: 99 }, (_, i) => archivo(`${i}.pdf`))
  const r = agregarArchivosMasivo(actuales, [archivo('x.pdf'), archivo('y.pdf')])
  assert.equal(r.archivos, actuales)
  assert.match(r.advertenciaLimite, /más de 100 CVs individuales/)
  // Los comprimidos no cuentan para el límite
  assert.equal(agregarArchivosMasivo(actuales, [archivo('lote.zip')]).archivos.length, 100)
})

test('carga masiva: el total no puede superar los 500 MB', () => {
  const r = agregarArchivosMasivo([archivo('a.zip', 400 * 1024 * 1024)], [archivo('b.zip', 101 * 1024 * 1024)])
  assert.equal(r.archivos.length, 1)
  assert.match(r.errores, /500 MB/)
})

test('avance real del lote: porcentaje y textos', () => {
  assert.equal(porcentajeLote(0, 0), 0)
  assert.equal(porcentajeLote(1, 3), 33)
  assert.equal(porcentajeLote(5, 4), 100)
  assert.equal(tituloProgreso('procesando', false), 'Procesando CVs...')
  assert.equal(tituloProgreso('procesando', true), 'Cancelando carga...')
  assert.equal(tituloProgreso('finalizado', false), 'Carga finalizada')
  assert.equal(tituloProgreso('cancelado', false), 'Carga cancelada')
  assert.equal(textoProgreso('procesando', 0, 0), 'Preparando archivos...')
  assert.equal(textoProgreso('procesando', 2, 7), 'Procesados 2 de 7 CVs')
})

test('lote cancelado: se informa lo procesado y lo ya creado', () => {
  assert.equal(
    mensajeCancelado({ procesados: 3, total: 10, reporte: { resumen: { creados: 2 } } }),
    'Carga cancelada. Se procesaron 3 de 10 CVs (los 2 candidato(s) ya creados se conservan).',
  )
  assert.equal(mensajeCancelado({ procesados: 0, total: 4, reporte: null }), 'Carga cancelada. Se procesaron 0 de 4 CVs.')
})

const RESUMEN = {
  total_archivos: 6, creados: 2, duplicados_omitidos: 1, sin_email: 0, rechazados_formato_tamano: 0,
  errores_lectura: 1, errores_validacion: 0, errores_persistencia: 0, errores_otros: 0,
}

test('resumen del lote: cuatro filas fijas y los errores de procesamiento solo si hubo', () => {
  const claves = categoriasResumen({ resumen: RESUMEN, resultados: [] }).map((c) => c.clave)
  assert.deepEqual(claves, ['creados', 'duplicados', 'sin-email', 'formato-tamano', 'errores-lectura'])
  assert.deepEqual(categoriasResumen(null), [])
})

test('resumen del lote: lista los archivos que no generaron un candidato', () => {
  const reporte = {
    resumen: RESUMEN,
    resultados: [
      { archivo: 'a.pdf', resultado: 'creado', mensaje: 'ok' },
      { archivo: 'b.pdf', resultado: 'duplicado', mensaje: 'ya existe' },
    ],
  }
  assert.deepEqual(detalleNoCreados(reporte).map((r) => r.archivo), ['b.pdf'])
})

// ---- Asignar a búsqueda ----

test('detalle del Smart Matching: faltantes y fórmula', () => {
  const texto = detalleMatch({
    id: '1', skills: ['Python', 'Django'], skills_coincidentes: ['python'], match_porcentaje: 65,
    seniority: 'Senior', seniority_compatible: true,
  })
  assert.match(texto, /Skills faltantes \(1\): Django/)
  assert.match(texto, /70% Skills \[50%\]\) \+ \(30% Seniority \[100%\]/)
  assert.match(texto, /Resultado final: 65% match/)
  assert.match(detalleMatch({ id: '2', skills: [] }), /100% Seniority/)
})
