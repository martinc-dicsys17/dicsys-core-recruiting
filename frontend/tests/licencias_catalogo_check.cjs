// node frontend/tests/licencias_catalogo_check.cjs
// Ejecuta el controlador real con respuestas HTTP simuladas, sin navegador.
const assert = require('node:assert/strict');
const vm = require('node:vm');
const { cargarScript } = require('./licencias_test_source.cjs');
let fetchResponse;
let urlRefrescada;
let toast;
let peticion;
let timerId = 0;
const timers = new Map();
const refrescos = [];
const context = vm.createContext({
  fetch: async (url, opciones) => { peticion = { url, opciones }; if (fetchResponse instanceof Error) throw fetchResponse; return fetchResponse; },
  htmx: { ajax: (_, url) => { urlRefrescada = url; refrescos.push(url); } },
  Alpine: { store: () => ({ error: mensaje => { toast = mensaje; }, success: mensaje => { toast = mensaje; } }) },
  setTimeout: (fn, ms) => { timers.set(++timerId, { fn, ms }); return timerId; },
  clearTimeout: id => timers.delete(id),
  URLSearchParams,
});
cargarScript('licencias_list.html', context);
const estado = context.licenciasFiltros();

(async () => {
  const herramienta = { id: 'h-1', proveedor_id: 'anterior', proveedor: 'Anterior' };
  const selector = { value: 'nuevo', disabled: false };
  fetchResponse = { status: 404, ok: false, json: async () => ({ detail: 'El proveedor no existe' }) };
  await estado.reapuntarProveedor(herramienta, selector);
  assert.equal(selector.value, 'anterior');
  assert.equal(selector.disabled, false);
  assert.equal(herramienta.proveedor_id, 'anterior');
  assert.equal(estado.errorCatalogo, 'El proveedor no existe');

  estado.herramientas = [herramienta];
  fetchResponse = new Error('offline');
  estado.borrarHerramienta(herramienta);
  await estado.confirmarBaja();
  assert.equal(estado.herramientas.length, 1);
  assert.match(estado.errorCatalogo, /Intentá nuevamente/);

  fetchResponse = { status: 204, ok: true };
  estado.borrarHerramienta(herramienta);
  await estado.confirmarBaja();
  assert.equal(estado.herramientas.length, 0);

  estado.buscar = 'A&B';
  estado.vista = 'equipos';
  estado.filtros = { equipo_ids: ['eq-1', 'eq-2'], proveedor_id: 'p-1', empleado_ids: ['emp-1', 'emp-2'] };
  estado.aplicarFiltros();
  assert.match(urlRefrescada, /vista=equipos/);
  assert(!urlRefrescada.includes('buscar='));
  assert.deepEqual(new URL(urlRefrescada, 'http://frontend.test').searchParams.getAll('equipo_id'), ['eq-1', 'eq-2']);
  assert.match(urlRefrescada, /equipo_id=eq-1/);
  assert.match(urlRefrescada, /proveedor_id=p-1/);
  assert.match(urlRefrescada, /empleado_id=emp-1/);
  assert.deepEqual(new URL(urlRefrescada, 'http://frontend.test').searchParams.getAll('empleado_id'), ['emp-1', 'emp-2']);

  estado.empleados = Array.from({ length: 250 }, (_, i) => ({
    id: `emp-${i}`, nombre: `Empleado ${i}`, codigo: `DEV-${String(i).padStart(3, '0')}`,
  }));
  estado.empleados[0].nombre = 'García, José';
  estado.empleados[1].nombre = 'Fernández, María';
  estado.filtros.empleado_ids = ['emp-249'];
  estado.buscar = 'JOSE garcia';
  assert.deepEqual(Array.from(estado.empleadosVisibles(), e => e.id), ['emp-0']);
  assert.deepEqual(Array.from(estado.filtros.empleado_ids), ['emp-249']);
  estado.alternarEmpleado('emp-0');
  assert.deepEqual(Array.from(estado.filtros.empleado_ids), ['emp-249', 'emp-0']);
  estado.buscar = 'maria dev-001';
  assert.deepEqual(Array.from(estado.empleadosVisibles(), e => e.id), ['emp-1']);
  estado.seleccionarResultadosEmpleados();
  estado.seleccionarResultadosEmpleados();
  assert.equal(estado.filtros.empleado_ids.length, 3);
  assert(estado.filtros.empleado_ids.includes('emp-249'));
  assert(estado.filtros.empleado_ids.includes('emp-0'));
  assert(estado.filtros.empleado_ids.includes('emp-1'));

  estado.buscar = '   ';
  assert.equal(estado.empleadosVisibles().length, 250);
  estado.seleccionarResultadosEmpleados();
  assert.equal(estado.filtros.empleado_ids.length, 250);
  const refrescosAntes = refrescos.length;
  assert.equal(timers.size, 1);
  const pendiente = [...timers.values()][0];
  assert.equal(pendiente.ms, 250);
  timers.clear();
  pendiente.fn();
  assert.equal(refrescos.length, refrescosAntes + 1);
  assert.equal(new URL(urlRefrescada, 'http://frontend.test').searchParams.getAll('empleado_id').length, 250);

  estado.limpiarEmpleados();
  assert.equal(estado.filtros.empleado_ids.length, 0);
  assert.equal(timers.size, 1);
  const limpieza = [...timers.values()][0];
  timers.clear();
  limpieza.fn();
  assert.equal(new URL(urlRefrescada, 'http://frontend.test').searchParams.getAll('empleado_id').length, 0);
  assert.match(urlRefrescada, /vista=equipos/);
  assert.match(urlRefrescada, /proveedor_id=p-1/);

  // Equipos superpuestos comparten personas: una sola asignación por empleado.
  estado.$nextTick = fn => fn();
  let foco;
  estado.$refs = {
    buscarDestinatarios: { focus() { foco = 'destinatarios'; } },
    herramientaLicencia: { focus() { foco = 'herramienta'; } },
  };
  estado.equipos = [
    { id: 'eq-1', nombre: 'Innovación', empleado_ids: ['emp-0', 'emp-1'] },
    { id: 'eq-2', nombre: 'Plataforma', empleado_ids: ['emp-1', 'emp-2'] },
    { id: 'eq-3', nombre: 'Vacío', empleado_ids: [] },
  ];
  estado.abrirNueva('emp-249', 'Persona de la fila');
  assert.deepEqual(Array.from(estado.nueva.empleado_ids), ['emp-249']);
  assert.equal(estado.empleadoFijo.nombre, 'Persona de la fila');
  assert.equal(foco, 'herramienta');
  estado.nueva.herramienta_id = 'h-1';
  estado.seguirCargando = true;
  fetchResponse = { ok: true, json: async () => ({ creadas: 1 }) };
  await estado.guardarNueva();
  assert.deepEqual(JSON.parse(peticion.opciones.body).empleado_ids, ['emp-249']);
  assert.equal(estado.empleadoFijo.id, 'emp-249');
  assert.deepEqual(Array.from(estado.nueva.empleado_ids), ['emp-249']);
  assert.equal(estado.nueva.herramienta_id, '');
  estado.abrirNueva();
  assert.equal(estado.empleadoFijo, null);
  assert.equal(estado.nueva.empleado_ids.length, 0);
  assert.equal(foco, 'destinatarios');
  estado.nueva.empleado_ids = ['emp-249'];
  estado.tipoDestinatario = 'equipos';
  estado.busquedaDestinatario = 'innovacion';
  assert.deepEqual(Array.from(estado.destinatariosVisibles(), e => e.id), ['eq-1']);
  estado.seleccionarDestinatariosVisibles();
  estado.busquedaDestinatario = 'plataforma';
  estado.seleccionarDestinatariosVisibles();
  assert.equal(estado.nueva.empleado_ids.length, 4);
  assert.equal(estado.destinatarioSeleccionado(estado.equipos[0]), true);
  assert.equal(estado.destinatarioSeleccionado(estado.equipos[2]), false);
  estado.tipoDestinatario = 'empleados';
  estado.busquedaDestinatario = 'jose garcia';
  estado.alternarDestinatario(estado.destinatariosVisibles()[0]);
  assert.equal(estado.nueva.empleado_ids.includes('emp-0'), false);
  estado.tipoDestinatario = 'equipos';
  assert.equal(estado.destinatarioSeleccionado(estado.equipos[0]), false);
  estado.alternarDestinatario(estado.equipos[0]);
  assert.equal(estado.nueva.empleado_ids.length, 4);
  estado.tipoDestinatario = 'empleados';
  estado.busquedaDestinatario = '';
  estado.soloSeleccionadosNueva = true;
  assert.equal(estado.destinatariosVisibles().length, 4);
  estado.soloSeleccionadosNueva = false;
  estado.seleccionarDestinatariosVisibles();
  assert.equal(estado.nueva.empleado_ids.length, 250);
  estado.nueva.herramienta_id = 'h-1';
  estado.nueva.costo_mensual = '12.50';
  const antesDeAsignar = refrescos.length;
  fetchResponse = { ok: false, json: async () => ({ detail: 'Un empleado no existe' }) };
  await estado.guardarNueva();
  assert.equal(estado.errorNueva, 'Un empleado no existe');
  assert.equal(estado.nueva.empleado_ids.length, 250);
  assert.equal(estado.showNueva, true);
  assert.equal(refrescos.length, antesDeAsignar);
  assert.equal(JSON.parse(peticion.opciones.body).empleado_ids.length, 250);
  assert.equal(JSON.parse(peticion.opciones.body).costo_mensual, '12.50');
  assert.equal(peticion.opciones.headers['Content-Type'], 'application/json');
  // Doble clic no inicia otro lote mientras el primero sigue pendiente.
  estado.guardandoNueva = true;
  const anterior = peticion;
  await estado.guardarNueva();
  assert.equal(peticion, anterior);
  estado.guardandoNueva = false;
  estado.seguirCargando = true;
  fetchResponse = { ok: true, json: async () => ({ creadas: 250 }) };
  await estado.guardarNueva();
  assert.equal(toast, '250 licencias asignadas');
  assert.equal(estado.nueva.empleado_ids.length, 250);
  assert.equal(estado.nueva.herramienta_id, '');
  assert.equal(estado.showNueva, true);
  assert.equal(refrescos.length, antesDeAsignar + 1);
  estado.nueva.herramienta_id = 'h-1';
  estado.seguirCargando = false;
  await estado.guardarNueva();
  assert.equal(estado.showNueva, false);

  estado.errorLicencia({ detail: { xhr: { responseText: '{"detail":"Licencia no encontrada"}' } } });
  assert.equal(toast, 'Licencia no encontrada');
  console.log('Catálogo, filtro y asignación múltiple: 250 empleados, equipos solapados, búsqueda, errores y guardado verificados.');
})().catch(error => { console.error(error); process.exitCode = 1; });
