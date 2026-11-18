// Pruebas de las reglas puras de Pipeline (embudo, modales, enlaces y vista global), sin navegador.
// Ejecutar desde frontend-vue/:  node --test tests/pipeline_reglas.test.mjs
import assert from 'node:assert/strict'
import test from 'node:test'

import {
  casoDeFila,
  conteoEtapa,
  destinosPermitidos,
  estadoAlAvanzar,
  estiloEtapa,
  etiquetaEtapa,
  filtrarPorEtapa,
  normalizarEtapaNombre,
  obtenerSiguienteEtapa,
  pideTransicionPretension,
  totalEnProceso,
} from '../src/modules/recruiting/pipeline/etapas.ts'
import {
  aplicarCambio,
  cambioAvance,
  cambioDescarte,
  cambioReingreso,
  errorAdjunto,
  formatearPretension,
  formularioCambio,
  idCandidato,
  tamanoAdjunto,
  validarPretension,
} from '../src/modules/recruiting/pipeline/movimientos.ts'
import {
  alcanceDesdeQuery,
  esMaximo,
  estiloCelda,
  filtrarFilas,
  formatoMoneda,
  idTarjeta,
  iniciales,
  inicialesPopup,
  queryDeAlcance,
  queryDeVista,
  searchSinFiltroDeEtapa,
  tituloColumna,
  urlColumna,
  urlPipeline,
  vistaDesdeQuery,
} from '../src/modules/recruiting/pipeline/presentacion.ts'

const cand = (etapa_actual, estado = 'En proceso', extra = {}) => ({
  id: `id-${etapa_actual}-${estado}`,
  candidato_id: `c-${etapa_actual}-${estado}`,
  etapa_actual,
  estado,
  ...extra,
})

// ---- Nombres de etapa y embudo ----

test('normaliza los nombres de etapa, incluidos los históricos', () => {
  assert.equal(normalizarEtapaNombre(''), 'Candidato')
  assert.equal(normalizarEtapaNombre(null), 'Candidato')
  assert.equal(normalizarEtapaNombre('Postulado'), 'Candidato')
  assert.equal(normalizarEtapaNombre('Coordinando entrevista'), 'Candidato')
  assert.equal(normalizarEtapaNombre(' screening '), 'Screening')
  assert.equal(normalizarEtapaNombre('Entrevista RRHH'), 'Entrevista RRHH')
  assert.equal(normalizarEtapaNombre('Entrevista Técnica'), 'Entrevista Líder Dicsys')
  assert.equal(normalizarEtapaNombre('Entrevista Lider Dicsys'), 'Entrevista Líder Dicsys')
  assert.equal(normalizarEtapaNombre('Validacion Administracion'), 'Validación Administración')
  assert.equal(normalizarEtapaNombre('Examen Medico'), 'Examen Médico Preocupacional')
  assert.equal(normalizarEtapaNombre('Presentacion Cliente'), 'Entrevista Cliente')
  assert.equal(normalizarEtapaNombre('Oferta'), 'Oferta')
  assert.equal(normalizarEtapaNombre('Ingreso'), 'Ingreso')
  assert.equal(normalizarEtapaNombre('Descartado'), 'Descartados')
  assert.equal(normalizarEtapaNombre('Otra cosa'), 'Otra cosa')
})

test('la siguiente etapa sigue el embudo; Ingreso y las desconocidas no avanzan', () => {
  assert.equal(obtenerSiguienteEtapa('Candidato'), 'Screening')
  assert.equal(obtenerSiguienteEtapa('Examen Médico Preocupacional'), 'Ingreso')
  assert.equal(obtenerSiguienteEtapa('Ingreso'), null)
  assert.equal(obtenerSiguienteEtapa('Descartados'), null)
  assert.equal(obtenerSiguienteEtapa('Otra cosa'), null)
})

test('destinos de Mover Etapa: la siguiente más los saltos permitidos', () => {
  assert.deepEqual(destinosPermitidos('Screening'), ['Entrevista RRHH'])
  assert.deepEqual(destinosPermitidos('Entrevista Líder Dicsys'), ['Validación Administración', 'Entrevista Cliente'])
  assert.deepEqual(destinosPermitidos('Validación Administración'), ['Entrevista Cliente', 'Oferta'])
  assert.deepEqual(destinosPermitidos('Entrevista Cliente'), ['Oferta', 'Examen Médico Preocupacional'])
  assert.deepEqual(destinosPermitidos('Ingreso'), [])
})

test('etiqueta abreviada de Entrevista Líder Dicsys en la barra de etapas', () => {
  assert.equal(etiquetaEtapa('Entrevista Líder Dicsys'), 'Entrevista Líder')
  assert.equal(etiquetaEtapa('Oferta'), 'Oferta')
})

test('Ingreso confirma el ingreso; el resto queda En proceso', () => {
  assert.equal(estadoAlAvanzar('Ingreso'), 'Ingreso confirmado')
  assert.equal(estadoAlAvanzar('Oferta'), 'En proceso')
})

test('la pretensión se pide solo de Entrevista RRHH a Entrevista Líder Dicsys', () => {
  assert.equal(pideTransicionPretension('Entrevista RRHH', 'Entrevista Líder Dicsys'), true)
  assert.equal(pideTransicionPretension('Screening', 'Entrevista RRHH'), false)
  assert.equal(pideTransicionPretension('Entrevista Líder Dicsys', 'Entrevista Cliente'), false)
})

// ---- Conteos y filtro por etapa ----

const LISTA = [
  cand('Candidato'),
  cand('Postulado'),
  cand('Screening'),
  cand('Descartados', 'Descartado'),
  cand('Screening', 'Descartado'),
  cand('Ingreso', 'Ingreso confirmado'),
]

test('cuenta y filtra por etapa: Descartados incluye los descartados por estado', () => {
  assert.equal(conteoEtapa(LISTA, 'Todas'), 6)
  assert.equal(conteoEtapa(LISTA, 'Candidato'), 2)
  assert.equal(conteoEtapa(LISTA, 'Screening'), 2)
  assert.equal(conteoEtapa(LISTA, 'Descartados'), 2)
  assert.equal(conteoEtapa(LISTA, 'Oferta'), 0)
  assert.equal(filtrarPorEtapa(LISTA, 'Todas'), LISTA)
  assert.deepEqual(
    filtrarPorEtapa(LISTA, 'Descartados').map((c) => c.estado),
    ['Descartado', 'Descartado'],
  )
})

test('total en proceso: excluye los descartados por estado o por etapa', () => {
  assert.equal(totalEnProceso(LISTA), 4)
})

test('caso de la fila: activo, Ingreso confirmado o descartado', () => {
  assert.equal(casoDeFila(cand('Screening')), 'activo')
  assert.equal(casoDeFila(cand('Ingreso', 'Ingreso confirmado')), 'ingreso')
  assert.equal(casoDeFila(cand('Descartados', 'Descartado')), 'descartado')
  assert.equal(casoDeFila(cand('Ingreso', 'descartado')), 'descartado')
})

test('colores de etapa: descartado por estado, por nombre y Screening por defecto', () => {
  assert.equal(estiloEtapa('Oferta', 'Descartado').badge, 'bg-rose-50 text-rose-700 border-rose-200')
  assert.equal(estiloEtapa('Descartados').tabActive, 'bg-rose-500 text-white border-rose-600 shadow-xs')
  assert.equal(estiloEtapa('descartado').tabActive, 'bg-rose-600 text-white border-rose-700 shadow-xs')
  assert.equal(estiloEtapa('Entrevista Técnica').dot, 'bg-indigo-500')
  assert.equal(estiloEtapa('Otra cosa').badge, 'bg-purple-50 text-purple-700 border-purple-200')
  assert.equal(estiloEtapa(null).badge, 'bg-purple-50 text-purple-700 border-purple-200')
  assert.equal(estiloEtapa('Todas').tabActive, 'bg-slate-800 text-white border-slate-900 shadow-xs')
})

// ---- Pretensión salarial y adjunto ----

test('la pretensión se formatea como moneda ARS mientras se escribe', () => {
  assert.equal(formatearPretension('1500000'), '$ 1.500.000')
  assert.equal(formatearPretension('$ 001.500a'), '$ 1.500')
  assert.equal(formatearPretension('abc'), '')
  assert.equal(formatearPretension('0'), '$ 0')
})

test('la pretensión es obligatoria, entera y mayor a cero', () => {
  assert.deepEqual(validarPretension(''), { valor: null, error: 'La pretensión salarial es obligatoria.' })
  assert.deepEqual(validarPretension('$ 0'), { valor: null, error: 'La pretensión salarial debe ser un importe mayor a cero.' })
  assert.deepEqual(validarPretension('12,5'), {
    valor: null,
    error: 'Ingresá un monto entero válido, sin decimales ni valores negativos.',
  })
  assert.deepEqual(validarPretension('$ 99.999.999.999.999.999'), { valor: null, error: 'El monto ingresado es demasiado grande.' })
  assert.deepEqual(validarPretension('$ 1.500.000'), { valor: 1500000, error: '' })
})

test('adjunto: hasta 10 MB y solo los formatos admitidos', () => {
  assert.equal(errorAdjunto({ name: 'informe.PDF', size: 1000 }), '')
  assert.equal(errorAdjunto({ name: 'datos.rar', size: 10 * 1024 * 1024 }), '')
  assert.equal(errorAdjunto({ name: 'grande.pdf', size: 10 * 1024 * 1024 + 1 }), 'El archivo supera el límite de 10 MB.')
  assert.match(errorAdjunto({ name: 'script.exe', size: 10 }), /^Tipo de archivo no permitido/)
  assert.equal(tamanoAdjunto(1536), '1.5 KB')
  assert.equal(tamanoAdjunto(2 * 1024 * 1024), '2.00 MB')
})

// ---- Lo que viaja al backend y cómo queda la fila ----

test('cuerpos de avance, descarte y reingreso', () => {
  assert.deepEqual(cambioAvance('Screening', 'En proceso', '', null), {
    etapa_actual: 'Screening',
    estado: 'En proceso',
    feedback_etapa: null,
  })
  assert.deepEqual(cambioAvance('Entrevista Líder Dicsys', 'En proceso', ' ok ', 2000), {
    etapa_actual: 'Entrevista Líder Dicsys',
    estado: 'En proceso',
    feedback_etapa: 'ok',
    pretension_salarial_bruta_ars: 2000,
  })
  assert.deepEqual(cambioDescarte(' No se presentó ', ''), {
    etapa_actual: 'Descartados',
    estado: 'Descartado',
    motivo_descarte: 'No se presentó',
    feedback_etapa: null,
  })
  assert.deepEqual(cambioReingreso('Cambió el perfil'), {
    etapa_actual: 'Entrevista RRHH',
    estado: 'En proceso',
    feedback_etapa: 'Cambió el perfil',
  })
})

test('el formulario multipart lleva los mismos campos y el archivo', () => {
  const f = formularioCambio(cambioAvance('Oferta', 'En proceso', '', 500), new Blob(['x']))
  assert.equal(f.get('etapa_actual'), 'Oferta')
  assert.equal(f.get('estado'), 'En proceso')
  assert.equal(f.get('feedback_etapa'), null)
  assert.equal(f.get('pretension_salarial_bruta_ars'), '500')
  assert.ok(f.get('archivo'))
})

test('la fila se actualiza en su lugar; el descarte guarda el motivo y el reingreso lo quita', () => {
  const lista = [cand('Screening', 'En proceso', { feedback_etapa: 'x' }), cand('Oferta')]
  const id = idCandidato(lista[0])
  const descartado = aplicarCambio(lista, id, cambioDescarte(' Motivo ', ' nota '), { motivo_descarte: ' Motivo ', feedback_etapa: ' nota ' })
  assert.equal(descartado[0].etapa_actual, 'Descartados')
  assert.equal(descartado[0].motivo_descarte, ' Motivo ')
  assert.equal(descartado[0].feedback_etapa, ' nota ')
  assert.equal(descartado[1], lista[1])
  const reingresado = aplicarCambio(descartado, id, cambioReingreso('perfil'))
  assert.equal(reingresado[0].etapa_actual, 'Entrevista RRHH')
  assert.equal(reingresado[0].estado, 'En proceso')
  assert.ok(!('motivo_descarte' in reingresado[0]))
  const avanzado = aplicarCambio(reingresado, id, cambioAvance('Entrevista Líder Dicsys', 'En proceso', '', 900))
  assert.equal(avanzado[0].pretension_salarial_bruta_ars, 900)
})

// ---- Enlaces y filtros de la URL ----

test('vista y filtro de candidatos desde la URL', () => {
  assert.equal(vistaDesdeQuery({}), 'global')
  assert.equal(vistaDesdeQuery({ vista: 'individual' }), 'individual')
  assert.equal(vistaDesdeQuery({ vista: 'otra' }), 'global')
  assert.equal(alcanceDesdeQuery({ alcance_candidatos: ' Propios ' }), 'propios')
  assert.equal(alcanceDesdeQuery({ alcance_candidatos: 'todos' }), '')
})

test('el selector de vista conserva el filtro; el filtro conserva el resto de los parámetros', () => {
  assert.deepEqual(queryDeVista('individual', { alcance_candidatos: 'propios', etapas: 'x' }), {
    vista: 'individual',
    alcance_candidatos: 'propios',
  })
  assert.deepEqual(queryDeVista('global', {}), {})
  assert.deepEqual(queryDeAlcance('', { vista: 'individual', alcance_candidatos: 'propios', etapas: 'Oferta' }), {
    vista: 'individual',
    etapas: 'Oferta',
    alcance_candidatos: '',
  })
})

test('enlaces al Pipeline individual (con filtro y columna de la vista global)', () => {
  assert.equal(urlPipeline('abc', ''), '/recruiting/oportunidades/abc/pipeline')
  assert.equal(urlPipeline('abc', 'propios'), '/recruiting/oportunidades/abc/pipeline?alcance_candidatos=propios')
  assert.equal(
    urlColumna({ id: 'abc' }, { clave: 'offer', nombre: 'Oferta', etapas: ['Oferta', 'Examen'], nota: null }, 'propios'),
    '/recruiting/oportunidades/abc/pipeline?etapas=Oferta%2CExamen&columna=Oferta&alcance_candidatos=propios',
  )
  assert.equal(searchSinFiltroDeEtapa('?etapas=a&columna=b&alcance_candidatos=propios'), '?alcance_candidatos=propios')
  assert.equal(searchSinFiltroDeEtapa('?etapas=a'), '')
})

// ---- Vista global ----

test('vista global: máximo de la fila, títulos, búsqueda por texto y formatos', () => {
  assert.equal(esMaximo({ columnas: { a: 2, b: 5 } }, 'b'), true)
  assert.equal(esMaximo({ columnas: { a: 2, b: 5 } }, 'a'), false)
  assert.equal(esMaximo({ columnas: { a: 0 } }, 'a'), false)
  assert.equal(tituloColumna({ nombre: 'Oferta', etapas: [], nota: null }), 'Oferta — Sin etapas asociadas')
  assert.equal(tituloColumna({ nombre: 'Oferta', etapas: ['Oferta', 'Examen'], nota: null }), 'Oferta — incluye: Oferta, Examen')
  assert.equal(estiloCelda('desconocida'), 'bg-dark-50 text-dark-700 hover:bg-dark-100 border-dark-200')
  const filas = [
    { titulo: 'Backend Python', cliente: 'Acme' },
    { titulo: 'QA', cliente: null },
  ]
  assert.equal(filtrarFilas(filas, ' acme ').length, 1)
  assert.equal(filtrarFilas(filas, '').length, 2)
  assert.equal(formatoMoneda(null), '—')
  assert.equal(formatoMoneda(1500000), '1.500.000 ARS')
  assert.equal(inicialesPopup('ana maria lopez'), 'AM')
  assert.equal(inicialesPopup(null), '?')
  assert.equal(iniciales('Beto Rios'), 'BR')
  assert.equal(iniciales('Beto'), 'BE')
  assert.equal(iniciales(''), 'C')
  assert.equal(idTarjeta({ id: '1234567890', id_busqueda: null }), '#12345678')
  assert.equal(idTarjeta({ id: 'x', id_busqueda: 'OP-1' }), '#OP-1')
})
