// Pruebas de las reglas puras de Nuevo Candidato (sin navegador ni dependencias nuevas).
// Ejecutar desde frontend-vue/:  node --test tests/candidato_nuevo_validacion.test.mjs
import assert from 'node:assert/strict'
import test from 'node:test'

import { nombreVisibleProvincia, nombresOrdenados, provinciasParaMostrar } from '../src/modules/recruiting/candidato-nuevo/catalogos.ts'
import {
  busquedaIdValido,
  destinoVolver,
  emailValido,
  enmascararFecha,
  errorArchivoCv,
  errorFechaNacimiento,
  fechaAIso,
  limpiarTelefono,
  armarAlta,
} from '../src/modules/recruiting/candidato-nuevo/validacion.ts'

const UUID = '3f0f6c1e-8a3b-4c52-9d0e-1a2b3c4d5e6f'

test('el teléfono solo admite dígitos y +', () => {
  assert.equal(limpiarTelefono('+54 9 (351) 123-4567 ab'), '+5493511234567')
})

test('la máscara de fecha arma DD-MM-AAAA y corta en 8 dígitos', () => {
  assert.equal(enmascararFecha('1'), '1')
  assert.equal(enmascararFecha('1503'), '15-03')
  assert.equal(enmascararFecha('15031990'), '15-03-1990')
  assert.equal(enmascararFecha('150319901234'), '15-03-1990')
})

test('fecha de nacimiento: vacía y válida no dan error', () => {
  assert.equal(errorFechaNacimiento(''), '')
  assert.equal(errorFechaNacimiento('15-03-1990'), '')
  assert.equal(errorFechaNacimiento('29-02-2000'), '') // bisiesto
})

test('fecha de nacimiento: inválidas', () => {
  assert.equal(errorFechaNacimiento('31-02-1990'), 'Fecha inválida')
  assert.equal(errorFechaNacimiento('15-13-1990'), 'Fecha inválida')
  assert.equal(errorFechaNacimiento('29-02-2001'), 'Fecha inválida')
  assert.equal(errorFechaNacimiento('hola'), 'Fecha inválida')
  assert.match(errorFechaNacimiento('01-01-1899'), /entre 1900 y 2010/)
  assert.match(errorFechaNacimiento('01-01-2011'), /entre 1900 y 2010/)
  assert.equal(errorFechaNacimiento('01-01-2010'), '')
})

test('la fecha se envía al backend como AAAA-MM-DD', () => {
  assert.equal(fechaAIso('05-03-1990'), '1990-03-05')
  assert.equal(fechaAIso('5/3/1990'), '1990-03-05')
  assert.equal(fechaAIso('1990-03-05'), '1990-03-05')
  assert.equal(fechaAIso(''), null)
})

test('email', () => {
  assert.equal(emailValido('ana@correo.com'), true)
  assert.equal(emailValido(' ana@correo.com '), true)
  assert.equal(emailValido('ana@correo'), false)
  assert.equal(emailValido('ana correo.com'), false)
})

test('archivo de CV: formato y tamaño', () => {
  assert.equal(errorArchivoCv({ name: 'cv.PDF', size: 1000 }), '')
  assert.equal(errorArchivoCv({ name: 'cv.docx', size: 2 * 1024 * 1024 }), '')
  assert.match(errorArchivoCv({ name: 'cv.txt', size: 10 }), /Formato inválido/)
  assert.match(errorArchivoCv({ name: 'sinextension', size: 10 }), /Formato inválido/)
  assert.match(errorArchivoCv({ name: 'cv.pdf', size: 2 * 1024 * 1024 + 1 }), /2 MB/)
})

test('id de búsqueda: solo UUID', () => {
  assert.equal(busquedaIdValido(UUID), UUID)
  assert.equal(busquedaIdValido('abc'), '')
  assert.equal(busquedaIdValido(undefined), '')
})

test('destino de Volver: solo rutas internas de Recruiting', () => {
  assert.equal(destinoVolver(undefined, ''), '/recruiting/candidatos')
  assert.equal(destinoVolver(undefined, UUID), `/recruiting/oportunidades/${UUID}`)
  assert.equal(destinoVolver('/recruiting/candidatos?page=2', ''), '/recruiting/candidatos?page=2')
  assert.equal(destinoVolver('/recruiting', ''), '/recruiting')
  for (const malo of [
    'https://malo.com',
    '//malo.com',
    '/otra/ruta',
    '/recruiting/../admin',
    '/recruiting/%2e%2e/admin',
    '/recruiting\\x',
    '/recruiting/\u0001',
    'recruiting/candidatos',
    '',
  ]) {
    assert.equal(destinoVolver(malo, ''), '/recruiting/candidatos', malo)
  }
})

test('provincias: Córdoba, Buenos Aires y el resto; «No identificada» se ve como «Otros»', () => {
  const p = (provincia_id, nombre) => ({ provincia_id, nombre, cantidad_ciudades: 1 })
  const nombres = provinciasParaMostrar([
    p(1, 'Salta'),
    p(2, 'No identificada'),
    p(3, 'Buenos Aires'),
    p(4, 'Cordoba'),
    p(5, 'Chaco'),
  ]).map((x) => x.nombre)
  assert.deepEqual(nombres, ['Cordoba', 'Buenos Aires', 'Chaco', 'Otros', 'Salta'])
  assert.equal(nombreVisibleProvincia('NO IDENTIFICADA'), 'Otros')
})

test('catálogos: nombres ordenados sin distinguir mayúsculas y sin vacíos', () => {
  assert.deepEqual(nombresOrdenados([{ nombre: 'python' }, { nombre: '' }, { nombre: 'Angular' }]), ['Angular', 'python'])
})

test('el alta arma CandidatoCreate y tolera el Puesto limpiado (null)', () => {
  const alta = armarAlta({
    nombre: ' Ana ', apellido: 'Paz', email: ' ana@x.com ', telefono: '', provincia_id: 1, ciudad_id: null,
    linkedin: '', dni: '', fecha_nacimiento: '05-03-1990', puesto: null, seniority: 'Junior', modalidad: 'Remoto',
    skills: ['Python'], habilidades: [],
  })
  assert.deepEqual(alta, {
    nombre: 'Ana', apellido: 'Paz', email: 'ana@x.com', telefono: null, provincia_id: 1, ciudad_id: null,
    dni: null, fecha_nacimiento: '1990-03-05', linkedin_url: null, headline: null, seniority: 'Junior',
    modalidad: 'Remoto', skills: ['Python'], habilidades: [], pretension_salarial: null,
    moneda_pretension: 'ARS', estado: 'Activo', fuente: 'Portal Propio',
  })
})
