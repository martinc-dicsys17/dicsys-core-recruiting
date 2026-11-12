// node --test frontend/tests/tareas_check.cjs
// Lógica del controlador Alpine de Configuración → Tareas programadas (F19).
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');
const vm = require('node:vm');

function controlador(globales = {}) {
  const ruta = path.resolve(__dirname, '../modulos/tareas/templates/tareas/list.html');
  const html = fs.readFileSync(ruta, 'utf8');
  const apertura = (html.match(/<script\b[^>]*>/g) || []).filter(a => !a.includes('type=') && !a.includes('src='));
  assert.equal(apertura.length, 1, 'Se esperaba un solo script de controlador');
  const inicio = html.indexOf(apertura[0]) + apertura[0].length;
  const script = html.slice(inicio, html.indexOf('</script>', inicio)).replace(/{{[\s\S]*?}}/g, 'null');
  const contexto = vm.createContext({ URLSearchParams, Date, setTimeout: () => 1, clearTimeout: () => {}, ...globales });
  vm.runInContext(script, contexto, { filename: ruta });
  return contexto.tareasProgramadas({ api: '/api', tab: 'tareas' });
}

test('duración, recorte y textos de estado', () => {
  const t = controlador();
  assert.equal(t.duracion({ inicio: '2026-10-05T09:00:00-03:00', fin: '2026-10-05T09:00:42-03:00' }), '42 s');
  assert.equal(t.duracion({ inicio: '2026-10-05T09:00:00-03:00', fin: '2026-10-05T09:03:05-03:00' }), '3 min 5 s');
  assert.equal(t.duracion({ estado: 'en_curso', inicio: '2026-10-05T09:00:00-03:00' }), 'Corriendo…');
  assert.equal(t.recortar('abcdef', 3), 'abc…');
  assert.equal(t.textoEstado('error'), 'Con error');
  assert.equal(t.textoEnvio({ estado: 'pendiente', intentos: 2 }), 'En cola · 2 intento(s)');
  assert.equal(t.textoEnvio({ estado: 'enviado', intentos: 1 }), 'Enviado');
  assert.equal(t.fecha(null), '—');
});

test('filtros del historial y refresco mientras algo corre', () => {
  const programados = [];
  const t = controlador({ setTimeout: (fn, ms) => programados.push(ms) });
  assert.equal(t.consulta({ tarea: 'cumpleanos', estado: '' }), '?tarea=cumpleanos');
  assert.equal(t.consulta({ tarea: '', estado: '' }), '');
  t.datos = { tareas: [{ codigo: 'a', en_curso: false }] };
  t.seguirSiHaceFalta();
  assert.deepEqual(programados, []);
  t.datos = { tareas: [{ codigo: 'a', en_curso: true }] };
  t.seguirSiHaceFalta();
  assert.deepEqual(programados, [5000]);
});
