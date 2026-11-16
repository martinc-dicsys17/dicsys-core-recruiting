// Pruebas de las reglas puras de Editar Candidato (sin navegador ni dependencias nuevas).
// Ejecutar desde frontend-vue/:  node --test tests/candidato_editar_formulario.test.mjs
import assert from 'node:assert/strict'
import test from 'node:test'

import {
  armarActualizacion,
  formatearSalario,
  formularioInicial,
  normalizarFechaAlSalir,
  prefijoMoneda,
} from '../src/modules/recruiting/candidato-editar/formulario.ts'

const CANDIDATO = {
  id: 'c1',
  nombre: 'Ana',
  apellido: 'Perez',
  email: 'ana@example.com',
  telefono: '+5493515550101',
  provincia_id: 1,
  ciudad_id: 10,
  fecha_nacimiento: '1990-05-17',
  headline: 'Desarrollador Backend',
  pretension_salarial: '1500000.00',
  moneda: 'USD',
  skills: ['Python'],
  habilidades: [],
}

test('el formulario inicial usa los valores por defecto de la ficha anterior', () => {
  const f = formularioInicial({ id: 'c2', nombre: 'Luz' }, null, null)
  assert.equal(f.seniority, 'Semi Senior')
  assert.equal(f.modalidad, 'Remoto')
  assert.equal(f.fuente, 'Portal Propio')
  assert.equal(f.disponibilidad, 'Inmediata')
  assert.equal(f.estado, 'Activo')
  assert.equal(f.moneda, 'ARS')
  assert.equal(f.salario, '')
  assert.equal(f.provincia_id, '')
})

test('el formulario inicial muestra la fecha DD-MM-AAAA, el salario con miles y la moneda guardada', () => {
  const f = formularioInicial(CANDIDATO, 1, 10)
  assert.equal(f.fecha_nacimiento, '17-05-1990')
  assert.equal(f.salario, (1500000).toLocaleString('es-AR'))
  assert.equal(f.moneda, 'USD')
  assert.equal(f.provincia_id, '1')
  assert.equal(f.ciudad_id, '10')
})

test('el salario deja solo dígitos con separador de miles y el prefijo sigue a la moneda', () => {
  assert.equal(formatearSalario('abc'), '')
  assert.equal(formatearSalario('1500000'), (1500000).toLocaleString('es-AR'))
  assert.equal(prefijoMoneda('USD'), 'US$')
  assert.equal(prefijoMoneda('ARS'), '$')
})

test('al salir del campo la fecha se completa con ceros', () => {
  assert.equal(normalizarFechaAlSalir('5-3-1990'), '05-03-1990')
  assert.equal(normalizarFechaAlSalir('5/3/1990'), '05-03-1990')
  assert.equal(normalizarFechaAlSalir('hola'), 'hola')
})

test('el cuerpo del PUT no envía provincia ni ciudad si no se modificaron', () => {
  const f = formularioInicial(CANDIDATO, 1, 10)
  const sin = armarActualizacion(f, false)
  assert.ok(!('provincia_id' in sin) && !('ciudad_id' in sin))
  const con = armarActualizacion({ ...f, ciudad_id: '' }, true)
  assert.equal(con.provincia_id, 1)
  assert.equal(con.ciudad_id, null)
})

test('el cuerpo del PUT limpia vacíos igual que la ficha anterior', () => {
  const f = formularioInicial(CANDIDATO, 1, 10)
  const cuerpo = armarActualizacion(
    { ...f, headline: '', dni: '  ', fuente: '', observaciones: '', salario: '', linkedin_url: '', fecha_nacimiento: '' },
    false,
  )
  assert.equal(cuerpo.headline, '') // vacío limpia el puesto
  assert.equal(cuerpo.dni, null)
  assert.equal(cuerpo.fuente, 'Portal Propio')
  assert.equal(cuerpo.observaciones, null)
  assert.equal(cuerpo.pretension_salarial, null)
  assert.equal(cuerpo.linkedin_url, null)
  assert.equal(cuerpo.fecha_nacimiento, null)
})

test('el cuerpo del PUT convierte la fecha a ISO y el salario a número, en ambas monedas', () => {
  const f = formularioInicial(CANDIDATO, 1, 10)
  const cuerpo = armarActualizacion(f, false)
  assert.equal(cuerpo.fecha_nacimiento, '1990-05-17')
  assert.equal(cuerpo.pretension_salarial, 1500000)
  assert.equal(cuerpo.moneda, 'USD')
  assert.equal(cuerpo.moneda_pretension, 'USD')
  assert.deepEqual(cuerpo.skills, ['Python'])
})
