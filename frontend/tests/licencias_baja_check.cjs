// node frontend/tests/licencias_baja_check.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { cargarScript } = require('./licencias_test_source.cjs');

const carpeta = path.join(__dirname, '../modulos/innovacion/templates/innovacion');
const template = fs.readFileSync(path.join(carpeta, 'licencias_list.html'), 'utf8');
const empleado = fs.readFileSync(path.join(carpeta, 'partials/licencias_empleado.html'), 'utf8');
assert(!empleado.includes('hx-confirm'));
assert(!empleado.includes('hx-delete'));
assert(!/\bconfirm\(/.test(template));
assert(template.includes('innovacion/partials/licencias_quitar.html'));
let respuesta;
let refrescos = 0;
let focoDevuelto = 0;
const llamadas = [];
const contexto = vm.createContext({
  fetch: async (url, opciones) => {
    llamadas.push({ url, opciones });
    if (respuesta instanceof Error) throw respuesta;
    return respuesta;
  },
});
cargarScript('licencias_list.html', contexto);
const estado = contexto.licenciasFiltros();
estado.aplicarFiltros = () => { refrescos++; };
estado.$nextTick = fn => fn();
estado.$refs = { cancelarBaja: { focus() {} }, bajaDialogo: { focus() {} } };
const boton = {
  dataset: { url: '/innovacion/licencias/lic-1', herramienta: 'Editor "Pro"', empleado: "O'Connor, Ana" },
  focus: () => { focoDevuelto++; },
};

(async () => {
  estado.borrarLicencia(boton);
  assert.equal(estado.bajaPendiente.nombre, 'Editor "Pro"');
  assert.equal(estado.bajaPendiente.empleado, "O'Connor, Ana");
  assert.equal(llamadas.length, 0);
  estado.cancelarBaja();
  assert.equal(estado.bajaPendiente, null);
  assert.equal(llamadas.length, 0);
  assert.equal(focoDevuelto, 1);

  estado.borrarLicencia(boton);
  let resolver;
  respuesta = new Promise(resolve => { resolver = resolve; });
  const pendiente = estado.confirmarBaja();
  await estado.confirmarBaja();
  estado.cancelarBaja();
  assert.equal(llamadas.length, 1);
  assert.equal(estado.confirmandoBaja, true);
  assert(estado.bajaPendiente);
  resolver({ ok: true, status: 200 }); // La baja de licencia devuelve 200 sin JSON.
  await pendiente;
  assert.equal(llamadas[0].url, '/innovacion/licencias/lic-1');
  assert.equal(llamadas[0].opciones.method, 'DELETE');
  assert.equal(estado.bajaPendiente, null);
  assert.equal(estado.confirmandoBaja, false);
  assert.equal(refrescos, 1);

  estado.herramientas = [{ id: 'h-1', nombre: 'Editor Pro' }];
  estado.borrarHerramienta(estado.herramientas[0]);
  respuesta = { ok: false, status: 500, json: async () => ({ detail: 'No se pudo completar la eliminación' }) };
  await estado.confirmarBaja();
  assert.equal(estado.herramientas.length, 1);
  assert(estado.bajaPendiente);
  assert.equal(estado.errorBaja, 'No se pudo completar la eliminación');
  respuesta = { ok: true, status: 204 };
  await estado.confirmarBaja();
  assert.equal(estado.herramientas.length, 0);
  assert.equal(estado.errorCatalogo, '');
  assert.equal(estado.bajaPendiente, null);

  estado.proveedores = [{ id: 'p-1', nombre: 'Proveedor' }];
  estado.proveedorEditando = { id: 'p-1', nombre: 'Proveedor' };
  estado.showProveedor = true;
  estado.filtros = { proveedor_id: 'p-1' };
  estado.borrarProveedor(estado.proveedores[0]);
  respuesta = new Error('offline');
  await estado.confirmarBaja();
  assert.equal(estado.proveedores.length, 1);
  assert.equal(estado.filtros.proveedor_id, 'p-1');
  assert.match(estado.errorBaja, /Intentá nuevamente/);
  respuesta = { ok: true, status: 204 };
  await estado.confirmarBaja();
  assert.equal(estado.proveedores.length, 0);
  assert.equal(estado.filtros.proveedor_id, '');
  assert.equal(estado.showProveedor, false);
  assert.equal(refrescos, 3);
  console.log('Modal de bajas: cancelar, confirmar una vez, errores y las tres bajas verificados.');
})().catch(error => { console.error(error); process.exitCode = 1; });
