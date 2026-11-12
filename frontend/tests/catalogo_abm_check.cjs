// node frontend/tests/catalogo_abm_check.cjs
const assert = require('node:assert/strict');
const vm = require('node:vm');
const { cargarScript } = require('./licencias_test_source.cjs');
let respuesta;
const llamadas = [];
const context = vm.createContext({
  fetch: async (url, opciones) => {
    llamadas.push({ url, method: opciones.method, payload: JSON.parse(opciones.body) });
    return respuesta;
  },
});
cargarScript('licencias_list.html', context);
const estado = context.licenciasFiltros();
estado.$nextTick = fn => fn();
estado.$refs = { nombreHerramienta: { focus() {} }, nombreProveedor: { focus() {} } };
estado.aplicarFiltros = () => {};
estado.herramientas = [{ id: 'h-1', nombre: 'ChatGTP', proveedor_id: 'p-1', proveedor: 'OenAI', costo_referencia: 10, moneda: 'USD' }];
estado.proveedores = [{ id: 'p-1', nombre: 'OenAI' }];
estado.nueva = { herramienta_id: 'otra', costo_mensual: '', moneda: 'ARS' };
const responder = (datos, status = 200) => { respuesta = { ok: status < 400, status, json: async () => datos }; };

(async () => {
  estado.showCatalogo = true;
  estado.abrirHerramienta(estado.herramientas[0]);
  estado.herramientaNueva.nombre = 'ChatGPT';
  estado.herramientaNueva.costo_referencia = '20,50';
  responder({ detail: 'Nombre ocupado' }, 409);
  await estado.guardarHerramienta();
  assert.equal(estado.showHerramienta, true);
  assert.equal(estado.errorHerramienta, 'Nombre ocupado');
  assert.equal(estado.herramientas[0].nombre, 'ChatGTP');
  assert.equal(llamadas.at(-1).method, 'PUT');
  assert.equal(llamadas.at(-1).url, '/innovacion/herramientas/h-1');

  estado.creandoProveedor = true;
  estado.herramientaNueva.proveedor_nombre = 'OpenAI';
  responder({ id: 'h-1', nombre: 'ChatGPT', proveedor_id: 'p-2', proveedor: 'OpenAI', costo_referencia: 20.5, moneda: 'USD' });
  await estado.guardarHerramienta();
  assert(!('proveedor_id' in llamadas.at(-1).payload));
  assert.equal(llamadas.at(-1).payload.proveedor_nombre, 'OpenAI');
  assert.equal(estado.herramientas.length, 1);
  assert.equal(estado.herramientas[0].nombre, 'ChatGPT');
  assert.equal(estado.nueva.herramienta_id, 'otra');
  assert.equal(estado.proveedores.length, 2);
  assert.equal(estado.showHerramienta, false);

  estado.abrirProveedor(estado.proveedores.find(p => p.id === 'p-2'));
  estado.proveedorEditando.nombre = 'OpenAI Inc.';
  responder({ detail: 'Nombre ocupado' }, 409);
  await estado.guardarProveedor();
  assert.equal(estado.showProveedor, true);
  assert.equal(estado.errorCatalogo, 'Nombre ocupado');
  assert.equal(estado.herramientas[0].proveedor, 'OpenAI');
  responder({ id: 'p-2', nombre: 'OpenAI Inc.' });
  await estado.guardarProveedor();
  assert.equal(llamadas.at(-1).method, 'PUT');
  assert.equal(estado.proveedores.length, 2);
  assert.equal(estado.herramientas[0].proveedor, 'OpenAI Inc.');
  assert.equal(estado.showProveedor, false);

  estado.abrirProveedor();
  estado.proveedorEditando.nombre = 'OpenAI Inc.';
  await estado.guardarProveedor();
  assert.equal(llamadas.at(-1).method, 'POST');
  assert.equal(estado.proveedores.length, 2); // POST reusa un nombre vigente.

  estado.showCatalogo = false;
  estado.showNueva = true;
  estado.abrirHerramienta();
  estado.herramientaNueva.nombre = 'Jira';
  responder({ id: 'h-2', nombre: 'Jira', costo_referencia: 30, moneda: 'USD' }, 201);
  await estado.guardarHerramienta();
  assert.equal(llamadas.at(-1).method, 'POST');
  assert.equal(estado.nueva.herramienta_id, 'h-2');
  assert.equal(estado.nueva.costo_mensual, '30');
  assert.equal(estado.nueva.moneda, 'USD');
  console.log('ABM Catálogo: alta, edición, errores y selección desde licencia verificados.');
})().catch(error => { console.error(error); process.exitCode = 1; });
