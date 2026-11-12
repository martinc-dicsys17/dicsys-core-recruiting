// node --test frontend/tests/licencias_comportamiento_check.cjs
const assert = require('node:assert/strict');
const { test } = require('node:test');
const vm = require('node:vm');
const { cargarScript } = require('./licencias_test_source.cjs');

function escenario() {
  const llamadas = [], refrescos = [], mensajes = [], focos = [], eventos = new Map();
  let respuesta = { ok: true, status: 200, json: async () => ({}) };
  const contexto = vm.createContext({
    fetch: async (url, opciones) => {
      llamadas.push({ url, ...opciones });
      if (respuesta instanceof Error) throw respuesta;
      return respuesta;
    },
    htmx: { ajax: (...args) => refrescos.push(args) },
    Alpine: { store: nombre => {
      assert.equal(nombre, 'toasts');
      return { error: mensaje => mensajes.push(mensaje), success: mensaje => mensajes.push(mensaje) };
    } },
    document: { querySelector: () => ({ dataset: { pagina: '3' } }), body: { addEventListener: (nombre, callback) => eventos.set(nombre, callback) } },
    setTimeout: () => 1,
    clearTimeout: () => {},
  });
  cargarScript('licencias_list.html', contexto);
  const estado = contexto.licenciasFiltros();
  estado.buscar = '';
  estado.vista = 'empleados';
  estado.filtros = { equipo_ids: [], proveedor_id: '', empleado_ids: [] };
  estado.empleados = [{ id: 'e1', nombre: 'Ana' }, { id: 'e2', nombre: 'José', codigo: 'DEV-2' }];
  estado.equipos = [{ id: 'q1', nombre: 'Equipo', empleado_ids: ['e1', 'e2'] }];
  estado.proveedores = [{ id: 'p1', nombre: 'Zulu' }, { id: 'p2', nombre: 'Alfa' }];
  estado.herramientas = [
    { id: 'h1', nombre: 'Editor', proveedor_id: 'p1', proveedor: 'Zulu', costo_referencia: 0, moneda: 'USD' },
    { id: 'h2', nombre: 'Agenda', proveedor_id: 'p2', proveedor: 'Alfa', costo_referencia: null },
    { id: 'h3', nombre: 'Chat' },
  ];
  estado.$nextTick = fn => fn();
  estado.$refs = Object.fromEntries(['nombreProveedor', 'nombreHerramienta', 'herramientaLicencia',
    'buscarDestinatarios', 'cancelarBaja', 'bajaDialogo'].map(nombre => [nombre, { focus: () => focos.push(nombre) }]));
  return {
    estado, llamadas, refrescos, mensajes, focos, eventos,
    responder: (datos, status = 200) => { respuesta = { ok: status < 400, status, json: async () => datos }; },
    responderCon: valor => { respuesta = valor; },
  };
}

test('eventos de licencia refrescan y abren una asignación con el nombre del empleado', () => {
  const { estado, eventos, refrescos, focos } = escenario();
  estado.init();
  eventos.get('licenciaEstadoCambiado')();
  assert.equal(refrescos.length, 1);
  assert.equal(refrescos[0][0], 'GET');
  assert.match(refrescos[0][1], /pagina=3/);
  assert.equal(refrescos[0][2].target, '#licencias-table');
  eventos.get('nueva-licencia-para')({ detail: { empleadoId: 'e1' } });
  assert.equal(estado.empleadoFijo.nombre, 'Ana');
  assert.equal(focos.at(-1), 'herramientaLicencia');
  const nueva = estado.nueva;
  estado.guardandoNueva = true;
  estado.abrirNueva('e2');
  estado.cerrarNueva();
  assert.equal(estado.nueva, nueva);
  assert.equal(estado.showNueva, true);
  estado.guardandoNueva = false;
  estado.showHerramienta = true;
  estado.cerrarNueva();
  assert.equal(estado.showNueva, false);
  assert.equal(estado.showHerramienta, false);
});

test('baja pendiente conserva su identidad mientras guarda y tolera referencias de foco ausentes', async () => {
  const { estado, llamadas, responder } = escenario();
  estado.cancelarBaja();
  await estado.confirmarBaja();
  assert.equal(llamadas.length, 0);
  delete estado.$nextTick;
  estado.borrarHerramienta(estado.herramientas[0]);
  const pendiente = estado.bajaPendiente;
  estado.confirmandoBaja = true;
  estado.borrarProveedor(estado.proveedores[0]);
  assert.equal(estado.bajaPendiente, pendiente);
  estado.confirmandoBaja = false;
  estado.cancelarBaja();
  assert.equal(estado.bajaPendiente, null);
  estado.$nextTick = fn => fn();
  delete estado.$refs;
  estado.borrarHerramienta(estado.herramientas[0]);
  responder({}, 204);
  await estado.confirmarBaja();
  assert.deepEqual(Array.from(estado.herramientas, h => h.id), ['h2', 'h3']);
  estado.$refs = {};
  estado.borrarProveedor(estado.proveedores[0]);
  await estado.confirmarBaja();
  assert.deepEqual(Array.from(estado.proveedores, p => p.id), ['p2']);
  assert.equal(estado.filtros.proveedor_id, '');
});

test('baja de licencia mantiene el modal en errores HTTP, JSON inválido y conexión', async () => {
  const { estado, responder, responderCon } = escenario();
  const boton = { dataset: { url: '/innovacion/licencias/l1', herramienta: 'Editor', empleado: 'Ana' } };
  for (const respuesta of [
    { ok: false, json: async () => { throw new SyntaxError('HTML'); } },
    { ok: false, json: async () => ({}) },
    new Error('offline'),
  ]) {
    estado.borrarLicencia(boton);
    estado.errorCatalogo = 'mensaje de catálogo';
    responderCon(respuesta);
    await estado.confirmarBaja();
    assert.equal(estado.bajaPendiente.url, boton.dataset.url);
    assert.equal(estado.confirmandoBaja, false);
    assert.equal(estado.errorCatalogo, 'mensaje de catálogo');
    assert.match(estado.errorBaja, /No se pudo/);
  }
  responder({ detail: 'Licencia inexistente' }, 404);
  await estado.confirmarBaja();
  assert.equal(estado.errorBaja, 'Licencia inexistente');
});

test('errores HTMX muestran detalle útil o un mensaje seguro cuando no hay JSON', () => {
  const { estado, mensajes } = escenario();
  for (const evento of [undefined, { detail: { xhr: { responseText: '{}' } } }]) {
    estado.errorLicencia(evento);
    assert.equal(mensajes.at(-1), 'No se pudo guardar el cambio de la licencia');
  }
});

test('proveedor valida nombre, evita doble envío y conserva formulario ante fallos', async () => {
  const { estado, llamadas, responder, responderCon } = escenario();
  estado.abrirProveedor();
  estado.proveedorEditando.nombre = '  ';
  await estado.guardarProveedor();
  assert.equal(llamadas.length, 0);
  assert.equal(estado.errorCatalogo, 'El nombre del proveedor es obligatorio');
  estado.proveedorEditando.nombre = '  Nuevo  ';
  let resolver;
  responderCon(new Promise(resolve => { resolver = resolve; }));
  const pendiente = estado.guardarProveedor();
  await estado.guardarProveedor();
  assert.equal(llamadas.length, 1);
  assert.deepEqual(JSON.parse(llamadas[0].body), { nombre: 'Nuevo' });
  resolver({ ok: false, status: 500, json: async () => ({}) });
  await pendiente;
  assert.equal(estado.errorCatalogo, 'No se pudo guardar el cambio');
  assert.equal(estado.guardandoProveedor, false);
  assert.equal(estado.showProveedor, true);
  for (const fallo of [new Error('offline'), { json: async () => { throw new SyntaxError('HTML'); } }]) {
    responderCon(fallo);
    await estado.guardarProveedor();
    assert.match(estado.errorCatalogo, /Intentá nuevamente/);
    assert.equal(estado.guardandoProveedor, false);
  }
  responder({ id: 'p1', nombre: 'Nuevo' });
  await estado.guardarProveedor();
  assert.deepEqual(Array.from(estado.proveedores, p => p.nombre), ['Alfa', 'Nuevo']);
  assert.equal(estado.herramientas[0].proveedor, 'Nuevo');
  assert.equal(estado.herramientas[1].proveedor, 'Alfa');
});

test('cambio de catálogo acepta 204 y reasignación actualiza o limpia proveedor y selector', async () => {
  const { estado, llamadas, refrescos, responder } = escenario();
  responder({}, 204);
  assert.deepEqual(Object.keys(await estado.cambiarCatalogo('/innovacion/proveedores/p1', { method: 'DELETE' })), []);
  const herramienta = estado.herramientas[0];
  const selector = { value: 'p2' };
  responder({ proveedor_id: 'p2', proveedor: 'Alfa' });
  await estado.reapuntarProveedor(herramienta, selector);
  assert.equal(herramienta.proveedor, 'Alfa');
  assert.equal(selector.value, 'p2');
  assert.deepEqual(JSON.parse(llamadas.at(-1).body), { proveedor_id: 'p2' });
  assert.equal(refrescos.length, 1);
  selector.value = '';
  responder({ proveedor_id: null, proveedor: null });
  await estado.reapuntarProveedor(herramienta, selector);
  assert.equal(herramienta.proveedor_id, null);
  assert.equal(selector.value, '');
  assert.equal(selector.disabled, false);
});

test('referencia de costo respeta cero y no pisa un importe escrito ni herramientas sin referencia', () => {
  const { estado } = escenario();
  estado.abrirNueva();
  for (const id of ['inexistente', 'h2', 'h3']) {
    estado.nueva.herramienta_id = id;
    estado.alElegirHerramienta();
    assert.equal(estado.nueva.costo_mensual, '');
  }
  estado.nueva.herramienta_id = 'h1';
  estado.alElegirHerramienta();
  assert.equal(estado.nueva.costo_mensual, '0');
  assert.equal(estado.nueva.moneda, 'USD');
  estado.nueva.costo_mensual = '18.50';
  estado.nueva.moneda = 'ARS';
  estado.alElegirHerramienta();
  assert.equal(estado.nueva.costo_mensual, '18.50');
  assert.equal(estado.nueva.moneda, 'ARS');
});

test('herramienta valida nombre, evita doble envío y conserva datos ante errores de servidor o red', async () => {
  const { estado, llamadas, responder, responderCon } = escenario();
  estado.abrirHerramienta();
  for (const nombre of [undefined, '   ']) {
    estado.herramientaNueva.nombre = nombre;
    await estado.guardarHerramienta();
    assert.equal(estado.errorHerramienta, 'El nombre es obligatorio');
  }
  assert.equal(llamadas.length, 0);
  estado.herramientaNueva.nombre = 'Nueva';
  let resolver;
  responderCon(new Promise(resolve => { resolver = resolve; }));
  const pendiente = estado.guardarHerramienta();
  await estado.guardarHerramienta();
  assert.equal(llamadas.length, 1);
  resolver({ ok: false, json: async () => ({}) });
  await pendiente;
  assert.equal(estado.errorHerramienta, 'No se pudo guardar la herramienta');
  for (const fallo of [new Error('offline'), { json: async () => { throw new SyntaxError('HTML'); } }]) {
    responderCon(fallo);
    await estado.guardarHerramienta();
    assert.equal(estado.errorHerramienta, 'Error de red al guardar la herramienta');
    assert.equal(estado.guardandoHerramienta, false);
    assert.equal(estado.showHerramienta, true);
  }
  responder({ id: 'h4', nombre: 'Nueva', proveedor_id: 'p1', proveedor: 'Zulu' });
  await estado.guardarHerramienta();
  assert.deepEqual(Array.from(estado.herramientas, h => h.nombre), ['Agenda', 'Chat', 'Editor', 'Nueva']);
  assert.equal(estado.proveedores.length, 2);
  assert.equal(estado.showHerramienta, false);
});

test('asignación valida todos los campos, limpia error HTML y advierte resultado incierto si falla red', async () => {
  const { estado, llamadas, refrescos, responder, responderCon } = escenario();
  estado.abrirNueva();
  for (const campos of [
    {}, { empleado_ids: ['e1'] }, { empleado_ids: ['e1'], herramienta_id: 'h1', fecha_inicio: '' },
  ]) {
    Object.assign(estado.nueva, campos);
    await estado.guardarNueva();
    assert.match(estado.errorNueva, /fecha de inicio/);
  }
  assert.equal(llamadas.length, 0);
  estado.nueva.fecha_inicio = '2026-09-06';
  responder({}, 422);
  await estado.guardarNueva();
  assert.equal(estado.errorNueva, 'No se pudieron asignar las licencias');
  responder({ detail: '  <b>Empleado inexistente</b>  ' }, 404);
  await estado.guardarNueva();
  assert.equal(estado.errorNueva, 'Empleado inexistente');
  for (const fallo of [new Error('offline'), { json: async () => { throw new SyntaxError('HTML'); } }]) {
    responderCon(fallo);
    await estado.guardarNueva();
    assert.match(estado.errorNueva, /Revisá el listado antes de volver a intentar/);
    assert.equal(estado.showNueva, true);
    assert.equal(estado.guardandoNueva, false);
    assert.equal(refrescos.length, 0);
  }
});

test('filtros cuentan dimensiones, deseleccionan una persona y recuperan etiquetas con fallback', () => {
  const { estado, refrescos } = escenario();
  assert.equal(Boolean(estado.tieneFilrosActivos()), false);
  assert.equal(estado.contarFiltros(), 0);
  estado.filtros.equipo_ids = ['q1'];
  assert.equal(Boolean(estado.tieneFilrosActivos()), true);
  assert.equal(estado.contarFiltros(), 1);
  estado.filtros.equipo_ids = [];
  estado.filtros.proveedor_id = 'p1';
  assert.equal(Boolean(estado.tieneFilrosActivos()), true);
  estado.filtros.proveedor_id = '';
  estado.filtros.empleado_ids = ['e1', 'e2'];
  assert.equal(Boolean(estado.tieneFilrosActivos()), true);
  estado.alternarEmpleado('e1');
  assert.deepEqual(Array.from(estado.filtros.empleado_ids), ['e2']);
  estado.filtros.equipo_ids = ['q1'];
  estado.filtros.proveedor_id = 'p1';
  assert.equal(estado.contarFiltros(), 3);
  for (const [metodo, id, nombre] of [
    ['getNombreEmpleado', 'e1', 'Ana'], ['getNombreEquipo', 'q1', 'Equipo'], ['getNombreProveedor', 'p2', 'Alfa'],
  ]) {
    assert.equal(estado[metodo](id), nombre);
    assert.equal(estado[metodo]('inexistente'), 'inexistente');
  }
  estado.buscar = 'Ana';
  estado.limpiarFiltros();
  assert.equal(estado.buscar, '');
  assert.equal(estado.contarFiltros(), 0);
  assert.equal(refrescos.length, 1);
  assert.equal(refrescos[0][1].split('?')[1], 'vista=empleados');
  assert.equal(estado.normalizarBusqueda(null), '');
});


for (const vista of ['empleados', 'equipos']) {
  test('activar y desactivar conserva desplegables en vista ' + vista, () => {
    const eventos = new Map();
    const claves = vista === 'empleados' ? [] : ['equipo-q1', 'equipo-q2', 'equipo-sin-equipo'];
    let nodos = claves.map((grupo, i) => ({ dataset: { grupo }, open: i < 2 }));
    const tabla = { id: 'licencias-table', querySelectorAll: () => nodos };
    const contexto = vm.createContext({
      document: { querySelector: () => ({ dataset: { pagina: '3' } }), body: { addEventListener: (nombre, fn) => eventos.set(nombre, fn) } },
      clearTimeout() {},
      htmx: { ajax: () => {
        eventos.get('htmx:beforeSwap')?.({ detail: { target: tabla, shouldSwap: true } });
        nodos = claves.map(grupo => ({ dataset: { grupo }, open: false }));
        eventos.get('htmx:afterSwap')?.({ detail: { target: tabla } });
      } },
    });
    cargarScript('licencias_list.html', contexto);
    const estado = contexto.licenciasFiltros();
    estado.vista = vista;
    estado.filtros = { empleado_ids: [], equipo_ids: [] };
    estado.init();
    eventos.get('licenciaEstadoCambiado')();
    assert.deepEqual(nodos.map(n => n.open), claves.map((_, i) => i < 2));
    // Una segunda operación respeta lo que el usuario cerró o abrió entre ambas.
    if (nodos.length) {
      nodos[0].open = false;
      nodos.at(-1).open = true;
    }
    const esperado = nodos.map(n => n.open);
    eventos.get('licenciaEstadoCambiado')();
    assert.deepEqual(nodos.map(n => n.open), esperado);
    // Un swap ajeno al listado no modifica su estado.
    const ajeno = { id: 'otro-modal', querySelectorAll: () => { throw Error('No es el listado'); } };
    eventos.get('htmx:beforeSwap')({ detail: { target: ajeno, shouldSwap: true } });
    eventos.get('htmx:afterSwap')({ detail: { target: ajeno } });
  });
}


test('baja de proveedor quita sus herramientas del selector y refresca sin filtro activo', async () => {
  const { estado, responder, refrescos } = escenario();
  estado.nueva.herramienta_id = 'h1';
  estado.borrarProveedor(estado.proveedores[0]);
  responder({}, 204);
  await estado.confirmarBaja();
  assert.deepEqual(Array.from(estado.herramientas, h => h.id), ['h2', 'h3']);
  assert.equal(estado.nueva.herramienta_id, '');
  assert.equal(refrescos.length, 1);
});

test('baja de herramienta limpia selección y actualiza métricas y asignaciones', async () => {
  const { estado, responder, refrescos } = escenario();
  estado.nueva.herramienta_id = 'h1';
  estado.borrarHerramienta(estado.herramientas[0]);
  responder({}, 204);
  await estado.confirmarBaja();
  assert.equal(estado.nueva.herramienta_id, '');
  assert.equal(refrescos.length, 1);
});


test('revocación confirma solo las asignaciones revisadas y conserva el catálogo', async () => {
  const { estado, responder, llamadas, refrescos } = escenario();
  estado.herramientaRevocar = 'h1';
  estado.filtros.equipo_ids = ['q1'];
  responder({ licencia_ids: ['l1', 'l2'], empleados: 2 });
  await estado.revisarRevocacion();
  assert.deepEqual(JSON.parse(llamadas[0].body), { herramienta_id: 'h1', empleado_ids: [], equipo_ids: ['q1'] });
  assert.equal(estado.bajaPendiente.tipo, 'lote');
  estado.filtros.equipo_ids = ['q2'];
  responder({ revocadas: 2 });
  await estado.confirmarBaja();
  assert.deepEqual(JSON.parse(llamadas[1].body), { licencia_ids: ['l1', 'l2'] });
  assert.equal(estado.herramientas.length, 3);
  assert.equal(refrescos.length, 1);
  assert.equal(estado.bajaPendiente, null);
});

test('revocación vacía o con error no abre confirmación', async () => {
  const { estado, responder } = escenario();
  estado.herramientaRevocar = 'h1';
  responder({ licencia_ids: [], empleados: 0 });
  await estado.revisarRevocacion();
  assert.match(estado.errorRevocacion, /No hay asignaciones/);
  assert.equal(estado.bajaPendiente, null);
  responder({ detail: 'Sin permiso' }, 403);
  await estado.revisarRevocacion();
  assert.equal(estado.errorRevocacion, 'Sin permiso');
  assert.equal(estado.revisandoRevocacion, false);
});


test('alta seleccionada deduplica equipos y envía varias herramientas con sus costos', async () => {
  const { estado, responder, llamadas } = escenario();
  estado.$refs.buscarAltaHerramientas = { focus() {} };
  estado.$refs.buscarDestinatarios = { focus() {} };
  estado.equipos.push({ id: 'q2', nombre: 'Otro', empleado_ids: ['e1'] });
  estado.filtros.equipo_ids = ['q1', 'q2'];
  estado.abrirAltaSeleccion();
  assert.deepEqual(Array.from(estado.nueva.empleado_ids), ['e1', 'e2']);
  estado.herramientasAlta = ['h1', 'h2'];
  estado.costosAlta.h2 = { costo_mensual: '123', moneda: 'USD' };
  responder({ creadas: 4 }, 201);
  await estado.guardarNueva();
  const payload = JSON.parse(llamadas[0].body);
  assert.equal(payload.licencias.length, 2);
  assert.equal(payload.licencias[0].costo_mensual, 0);
  assert.equal(payload.licencias[1].costo_mensual, '123');
  assert.equal(payload.licencias[1].moneda, 'USD');
  assert.equal(estado.showNueva, false);
});
