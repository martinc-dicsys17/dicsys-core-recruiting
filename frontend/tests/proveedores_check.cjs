// node --test frontend/tests/proveedores_check.cjs
// Lógica de los controladores Alpine de Administración → Proveedores.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');
const vm = require('node:vm');

// Los arrays y objetos del contexto vm son de otro realm: se comparan por su JSON
const plano = valor => JSON.parse(JSON.stringify(valor));

function controlador(plantilla, funcion, args = [], documento = {}, globales = {}) {
  const ruta = path.resolve(__dirname, '../modulos/administracion/templates/administracion', plantilla);
  const html = fs.readFileSync(ruta, 'utf8');
  // El script del controlador es el único sin type ni src (los type="application/json" son datos
  // y los src, librerías)
  const aperturas = (html.match(/<script\b[^>]*>/g) || []).filter(a => !a.includes('type=') && !a.includes('src='));
  assert.equal(aperturas.length, 1, `Se esperaba un solo script de controlador en ${plantilla}`);
  const inicio = html.indexOf(aperturas[0]) + aperturas[0].length;
  const script = html.slice(inicio, html.indexOf('</script>', inicio)).replace(/{{[\s\S]*?}}/g, 'null');
  const document = { getElementById: id => (id in documento ? { textContent: documento[id] } : null) };
  const contexto = vm.createContext({ lucide: { createIcons: () => {} }, URLSearchParams, Date, document, ...globales });
  vm.runInContext(script, contexto, { filename: ruta });
  return contexto[funcion](...args);
}

const ITEMS = [
  { id: '1', proveedor: { nombre: 'ODOO' }, evaluador: { id: 'e1' }, evaluado: true, con_hallazgo: true },
  { id: '2', proveedor: { nombre: 'Banco Galicia' }, evaluador: { id: 'e2' }, evaluado: false, con_hallazgo: false },
  { id: '3', proveedor: { nombre: 'Sin dueño' }, evaluador: null, evaluado: false, con_hallazgo: false },
];

test('tablero: filtros por texto, estado, hallazgos y evaluador', () => {
  const tablero = controlador('evaluaciones_proveedores.html', 'evaluacionProveedores', ['/base']);
  tablero.datos = { items: ITEMS, metricas: { total: 3, evaluados: 1, pendientes: 2, con_hallazgo: 1 } };
  const ids = () => plano(tablero.itemsVista().map(i => i.id));

  assert.deepEqual(ids(), ['1', '2', '3']);
  tablero.filtros.texto = ' gali ';
  assert.deepEqual(ids(), ['2']);
  tablero.filtros.texto = 'GALICÍA';  // sin importar mayúsculas ni acentos
  assert.deepEqual(ids(), ['2']);
  tablero.filtros = { texto: '', estado: 'pendientes', evaluador: '' };
  assert.deepEqual(ids(), ['2', '3']);
  tablero.filtros.estado = 'hallazgos';
  assert.deepEqual(ids(), ['1']);
  tablero.filtros = { texto: '', estado: 'todos', evaluador: 'sin' };
  assert.deepEqual(ids(), ['3']);
  tablero.filtros.evaluador = 'e2';
  assert.deepEqual(ids(), ['2']);
  assert.deepEqual(plano(tablero.metricas().map(m => [m.filtro, m.valor])),
    [['todos', 3], ['evaluados', 1], ['pendientes', 2], ['hallazgos', 1]]);
});

test('tablero: fechas, colores y estados', () => {
  const tablero = controlador('evaluaciones_proveedores.html', 'evaluacionProveedores', ['/base']);
  assert.equal(tablero.fecha('2026-10-15'), '15/10/2026');
  assert.equal(tablero.fecha(null), '');
  assert.match(tablero.fecha('2026-10-15T12:00:00'), /15\/10\/2026|15\/10\/26/);
  assert.equal(tablero.claseValor('Si'), 'bg-red-100 text-red-700');
  assert.equal(tablero.claseValor('No'), 'bg-emerald-100 text-emerald-700');
  assert.equal(tablero.textoEstado('reemplazada'), 'Finalizada');
});

test('agregar proveedor: busca en el registro y vale la última respuesta', async () => {
  const tablero = controlador('evaluaciones_proveedores.html', 'evaluacionProveedores', ['/base']);
  tablero.$nextTick = () => {};
  tablero.datos = { es_admin: true, evaluacion: { activa: true }, items: [] };
  const pedidos = [];
  tablero.pedir = ruta => new Promise(resolver => pedidos.push({ ruta, resolver }));
  const galicia = { id: 'p2', nombre: 'Banco Galicía', tipo: 'proveedor', cuit: '30-50000173-5', referente: null,
    activo: true, en_evaluacion: true };

  tablero.agregar.buscar = 'ga';
  const primera = tablero.buscarCandidatos();
  tablero.agregar.buscar = ' gal ';
  const segunda = tablero.buscarCandidatos();
  assert.equal(pedidos[1].ruta, 'candidatos?buscar=gal');
  pedidos[1].resolver({ total: 1, items: [galicia] });
  await segunda;
  pedidos[0].resolver({ total: 9, items: [] });  // llega tarde: no pisa la última búsqueda
  await primera;
  assert.deepEqual(plano(tablero.agregar.candidatos.map(c => c.nombre)), ['Banco Galicía']);
  assert.equal(tablero.agregar.total, 1);
  assert.equal(tablero.agregar.buscando, false);

  assert.equal(tablero.detalleCandidato(galicia), 'Proveedor · 30-50000173-5 · Referente sin definir');
  tablero.agregar.buscar = ' survey ';
  assert.equal(tablero.textoSinResultados(), 'No hay proveedores en el registro que coincidan con «survey».');
});

test('agregar proveedores: se eligen varios con Agregar/Agregado y se suman juntos', async () => {
  const confirmaciones = [];
  const toasts = [];
  const tablero = controlador('evaluaciones_proveedores.html', 'evaluacionProveedores', ['/base'], {}, {
    confirm: texto => { confirmaciones.push(texto); return true; },
    Alpine: { store: () => ({ success: texto => toasts.push(texto) }) },
  });
  tablero.datos = { es_admin: true, evaluacion: { activa: true }, items: [] };
  const pedidos = [];
  tablero.pedir = async (ruta, opciones) => { pedidos.push({ ruta, cuerpo: JSON.parse(opciones.body) });
    return { agregados: [{ id: 'i1' }, { id: 'i2' }] }; };
  tablero.cargar = async () => {};
  const odoo = { id: 'p1', nombre: 'ODOO', activo: true };
  const webmail = { id: 'p2', nombre: 'Webmail', activo: true };

  assert.equal(tablero.textoBotonAgregar(), 'Agregar');
  tablero.alternar(odoo);
  assert.equal(tablero.estaElegido(odoo), true);
  tablero.agregar.candidatos = [];  // otra búsqueda: lo elegido se conserva
  tablero.alternar(webmail);
  assert.equal(tablero.textoBotonAgregar(), 'Agregar (2)');
  assert.equal(tablero.textoElegidos(), '2 elegidos');
  tablero.alternar(webmail);  // el mismo botón lo vuelve a «Agregar»
  assert.equal(tablero.estaElegido(webmail), false);
  tablero.alternar(webmail);

  tablero.agregar.abierto = true;
  await tablero.agregarElegidos();
  assert.deepEqual(plano(pedidos), [{ ruta: 'items', cuerpo: { proveedor_ids: ['p1', 'p2'] } }]);
  assert.deepEqual(confirmaciones, []);  // ya no se reactiva nada al agregar: un inactivo no se puede elegir
  assert.deepEqual(toasts, ['2 proveedores agregados a la evaluación']);
  assert.equal(tablero.agregar.abierto, false);
});

test('agregar proveedor: el admin y el evaluador con empleado; textos de cada uno', () => {
  const tablero = controlador('evaluaciones_proveedores.html', 'evaluacionProveedores', ['/base']);
  const con = datos => { tablero.datos = { items: [], evaluacion: { activa: true }, ...datos }; return tablero; };

  assert.equal(con({ es_admin: true, empleado_vinculado: false }).puedeAgregar(), true);
  assert.equal(con({ es_admin: false, empleado_vinculado: true }).puedeAgregar(), true);
  assert.equal(con({ es_admin: false, empleado_vinculado: false }).puedeAgregar(), false);
  assert.equal(con({ es_admin: true, evaluacion: { activa: false } }).puedeAgregar(), false);

  // La evaluación vacía explica cómo se suman los proveedores
  assert.match(con({ es_admin: true }).textoSinItems(), /importalos desde el Google Sheet/);
  assert.match(con({ es_admin: false, empleado_vinculado: true }).textoSinItems(), /los que tenés asignados/);
  tablero.agregar.buscar = '';
  assert.equal(tablero.textoSinResultados(), 'No tenés proveedores asignados como usuario referente.');
  tablero.agregar.buscar = 'odoo';
  assert.equal(tablero.textoSinResultados(), 'No tenés proveedores asignados que coincidan con «odoo».');
});

test('formulario de evaluación: exige las dos preguntas', () => {
  const item = JSON.stringify({ id: 'i1', preguntas: ['incidentes', 'mal_manejo'], opciones: {},
    incidentes: 'No', mal_manejo: null });
  const form = controlador('evaluacion_proveedor_form.html', 'formularioEvaluacion', ['/base'], { 'evaluacion-datos': item });
  assert.deepEqual(plano(form.faltan()), ['mal_manejo']);
  form.valores.mal_manejo = 'No';
  assert.deepEqual(plano(form.faltan()), []);
  assert.equal('checklist' in form.valores, false);
});

test('formulario de evaluación: la evidencia se pide solo con «Si» y se descarta si no', () => {
  const item = JSON.stringify({ id: 'i1', preguntas: ['incidentes', 'mal_manejo'], opciones: {},
    incidentes: 'No', mal_manejo: 'Si', evidencia_incidentes: 'vieja', evidencia_mal_manejo: 'https://drive/x' });
  const form = controlador('evaluacion_proveedor_form.html', 'formularioEvaluacion', ['/base'], { 'evaluacion-datos': item });
  const enfocados = [];
  form.$nextTick = funcion => funcion();
  assert.equal(form.pideEvidencia('incidentes'), false);
  assert.equal(form.pideEvidencia('mal_manejo'), true);
  assert.deepEqual(plano(form.faltanEvidencias()), []);
  // Con «No» la evidencia no viaja aunque hubiera texto
  assert.deepEqual(plano(form.cuerpo()), {
    incidentes: 'No', mal_manejo: 'Si', evidencia_incidentes: null, evidencia_mal_manejo: 'https://drive/x',
  });
  form.valores.incidentes = 'N/A';
  assert.equal(form.pideEvidencia('incidentes'), false);
  form.elegir('incidentes', 'Si');
  form.evidencias.incidentes = '   ';
  assert.deepEqual(plano(form.faltanEvidencias()), ['incidentes']);
  form.evidencias.incidentes = ' ticket #12 ';
  assert.equal(form.cuerpo().evidencia_incidentes, 'ticket #12');
  form.elegir('mal_manejo', 'No');
  assert.equal(form.cuerpo().evidencia_mal_manejo, null);
});

test('formulario de evaluación: si falta una respuesta o su evidencia avisa arriba y sube la página', async () => {
  const item = JSON.stringify({ id: 'i1', preguntas: ['incidentes', 'mal_manejo'], opciones: {}, incidentes: 'Si' });
  const desplazamientos = [];
  const pedidos = [];
  const form = controlador('evaluacion_proveedor_form.html', 'formularioEvaluacion', ['/base'], { 'evaluacion-datos': item },
    { window: { scrollTo: opciones => desplazamientos.push(opciones) }, fetch: (...args) => pedidos.push(args) });
  await form.guardar();
  assert.equal(form.error, 'Falta responder: Proveedores: ¿hubo mal manejo de información compartida?');
  form.valores.mal_manejo = 'No';
  await form.guardar();
  assert.equal(form.error, 'Con «Si» la evidencia es obligatoria: Herramientas: ¿hubo incidentes?');
  assert.deepEqual(plano(desplazamientos), [{ top: 0, behavior: 'smooth' }, { top: 0, behavior: 'smooth' }]);
  assert.equal(pedidos.length, 0);
});

test('registro: el listado arranca con los filtros de activos', () => {
  const registro = controlador('proveedores_list.html', 'registroProveedores', ['/api']);
  assert.deepEqual(plano(registro.filtros), { buscar: '', tipo: '', estado: 'activos', sin_referente: false });
  assert.equal(registro.TIPOS.herramienta, 'Herramienta');
  assert.equal(registro.dominio('https://www.odoo.com/'), 'www.odoo.com');
  assert.equal(registro.dominio(null), '');
});

const PROVEEDOR = JSON.stringify({
  id: 'p1', nombre: 'ODOO', tipo: 'herramienta', acuerdo_servicio: null, politica_nda_archivo_nombre: 'nda.pdf',
  referente: { id: 'e1', nombre: 'Vega, Federico' }, oficinas: [{ id: 'o1' }], contactos: [],
});
const formulario = datos => controlador('proveedores_form.html', 'formularioProveedor',
  [{ api: '/api', lista: '/administracion/proveedores' }], { 'proveedor-datos': datos });

test('formulario de edición: carga los datos, el referente y el adjunto', () => {
  const form = formulario(PROVEEDOR);
  assert.equal(form.id, 'p1');
  assert.equal(form.datos.nombre, 'ODOO');
  assert.equal(form.datos.acuerdo_servicio, '');
  assert.equal(form.datos.referente_empleado_id, 'e1');
  assert.equal(form.adjunto, 'nda.pdf');
  assert.equal(form.urlNda, '/administracion/proveedores/p1/nda');
  assert.equal(form.oficinas.length, 1);
  assert.equal(form.cuerpo().acuerdo_servicio, null);
});

test('formulario de alta: vacío y sin adjunto', () => {
  const form = formulario('{}');
  assert.equal(form.id, null);
  assert.equal(form.datos.tipo, 'sin_clasificar');
  assert.equal(form.urlNda, null);
  assert.equal(form.adjunto, null);
});

// DOM mínimo del formulario: cada control sabe su pestaña, su campo y si el navegador lo marca inválido
function campoFalso(pestana, { invalido = false, campo = null, valor = '', tipo = 'text' } = {}) {
  const control = {
    willValidate: true, invalido, value: valor, type: tipo, avisos: 0, enfocado: false, desplazado: false, eventos: [],
    closest: selector => (selector === '[data-tab]' ? { dataset: { tab: pestana } }
      : selector === '[data-campo]' && campo ? { dataset: { campo } } : null),
    reportValidity() { this.avisos += 1; },
    scrollIntoView() { this.desplazado = true; },
    querySelector: () => ({ focus: () => { control.enfocado = true; } }),
    dispatchEvent(evento) { this.eventos.push(evento.type); },
  };
  return control;
}
function formFalso(controles, contenedores = {}) {
  return {
    querySelectorAll: selector => (selector === ':invalid' ? controles.filter(c => c.invalido)
      : selector.includes('[required]') ? controles.filter(c => c.requerido) : []),
    querySelector: selector => contenedores[(selector.match(/data-campo="(.+)"/) || [])[1]] || null,
  };
}
const eventoInvalido = () => ({ prevenido: false, preventDefault() { this.prevenido = true; } });

test('formulario de edición: con acuerdo firmado no se guarda sin el adjunto', async () => {
  const pedidos = [];
  const form = controlador('proveedores_form.html', 'formularioProveedor',
    [{ api: '/api', lista: '/administracion/proveedores' }],
    { 'proveedor-datos': JSON.stringify({ id: 'p1', nombre: 'ODOO', acuerdo_servicio: 'Si', politica_nda_archivo_nombre: null }) },
    { window: { scrollTo: () => {} }, fetch: async (...args) => { pedidos.push(args); } });
  form.$nextTick = funcion => funcion();
  const adjunto = campoFalso('seguridad');
  form.$refs = { form: formFalso([], { adjunto }) };
  assert.equal(form.acuerdoGuardado, 'Si');  // con Sí guardado el adjunto no se puede quitar
  assert.equal(form.faltaAdjunto(), true);
  form.tab = 'datos';
  await form.guardar();
  // Abre Seguridad, marca el adjunto y lo lleva a la vista
  assert.equal(form.tab, 'seguridad');
  assert.match(form.errores.adjunto, /adjunto es obligatorio/);
  assert.equal(adjunto.desplazado && adjunto.enfocado, true);
  assert.deepEqual(plano(form.pestanasConError), ['seguridad']);
  assert.equal(pedidos.length, 0);
  form.datos.acuerdo_servicio = 'No';
  assert.equal(form.faltaAdjunto(), false);
  form.datos.acuerdo_servicio = 'Si';
  form.adjunto = 'acuerdo.pdf';
  assert.equal(form.faltaAdjunto(), false);
});

test('formulario de alta con acuerdo firmado: los datos y el archivo viajan juntos', async () => {
  const pedidos = [];
  const ventana = { scrollTo: () => {}, location: {} };
  const fetch = async (url, opciones) => { pedidos.push([url, opciones]); return { ok: true, json: async () => ({ id: 'p9' }) }; };
  const form = controlador('proveedores_form.html', 'formularioProveedor',
    [{ api: '/api', lista: '/administracion/proveedores', altaConAdjunto: '/alta-con-adjunto' }],
    { 'proveedor-datos': '{}' }, { window: ventana, fetch, FormData });
  assert.equal(form.faltaAdjunto(), false);  // en el alta lo controla el input required
  form.datos.nombre = 'ODOO';
  form.datos.acuerdo_servicio = 'Si';
  form.archivoNda = 'contenido';
  await form.guardar();
  assert.equal(pedidos.length, 1);
  assert.equal(pedidos[0][0], '/alta-con-adjunto');
  assert.equal(JSON.parse(pedidos[0][1].body.get('datos')).acuerdo_servicio, 'Si');
  assert.equal(pedidos[0][1].body.get('archivo'), 'contenido');
  assert.equal(ventana.location.href, '/administracion/proveedores/p9/editar?ok=creado');
});

test('formulario: al guardar con inválidos abre la pestaña del que falta y muestra su aviso', () => {
  const esperas = [];
  const form = controlador('proveedores_form.html', 'formularioProveedor',
    [{ api: '/api', lista: '/administracion/proveedores' }], { 'proveedor-datos': PROVEEDOR },
    { setTimeout: funcion => esperas.push(funcion) });
  form.$nextTick = funcion => funcion();
  const servicio = campoFalso('datos', { invalido: true });
  const email = campoFalso('contacto');
  const politica = campoFalso('seguridad', { invalido: true });
  form.$refs = { form: formFalso([servicio, email, politica]) };
  assert.deepEqual(plano(form.PESTANAS_FORM), ['datos', 'contacto', 'seguridad']);

  // El navegador avisa una vez por cada inválido: se cancelan sus avisos y se resuelve una sola vez
  form.tab = 'contacto';
  const eventos = [eventoInvalido(), eventoInvalido()];
  eventos.forEach(e => form.alInvalido(e));
  assert.equal(eventos.every(e => e.prevenido), true);
  assert.equal(esperas.length, 1);
  esperas[0]();
  assert.equal(form.tab, 'datos');  // ninguno en la pestaña abierta: el primero del formulario
  assert.equal(servicio.avisos, 1);

  // Si hay uno en la pestaña abierta, se queda ahí
  form.tab = 'seguridad';
  form.alInvalido(eventoInvalido());
  esperas[1]();
  assert.equal(form.tab, 'seguridad');
  assert.equal(politica.avisos, 1);

  // El aviso que muestra el formulario no se vuelve a interceptar
  form.mostrandoAviso = true;
  const propio = eventoInvalido();
  form.alInvalido(propio);
  assert.equal(propio.prevenido, false);
});

test('formulario: al guardar marca las pestañas con errores y un obligatorio con solo espacios cuenta como vacío', () => {
  const form = controlador('proveedores_form.html', 'formularioProveedor',
    [{ api: '/api', lista: '/administracion/proveedores' }], { 'proveedor-datos': PROVEEDOR },
    { Event: class { constructor(tipo) { this.type = tipo; } } });
  form.$nextTick = funcion => funcion();
  const espacios = Object.assign(campoFalso('datos', { invalido: true, valor: '   ', campo: 'servicio_provisto' }), { requerido: true });
  const archivo = Object.assign(campoFalso('seguridad', { invalido: true, valor: '', tipo: 'file' }), { requerido: true });
  form.$refs = { form: formFalso([espacios, archivo]) };
  form.errores = { nombre: 'viejo' };

  form.alPresionarGuardar();

  assert.equal(form.intentado, true);
  assert.deepEqual(plano(form.errores), {});  // las marcas del servidor se limpian en cada intento
  assert.equal(espacios.value, '');
  assert.deepEqual(espacios.eventos, ['input']);  // para que x-model se entere
  assert.deepEqual(plano(form.pestanasConError), ['datos', 'seguridad']);
  assert.equal(form.pestanaConError('contacto'), false);

  // Al corregir, la pestaña deja de marcarse
  espacios.invalido = false;
  form.revisar({ target: espacios });
  assert.deepEqual(plano(form.pestanasConError), ['seguridad']);
});

test('formulario: los errores del servidor se marcan en su campo y llevan a su pestaña', async () => {
  const { erroresPorCampo } = formulario(PROVEEDOR);
  assert.deepEqual(plano(erroresPorCampo('Faltan datos obligatorios: usuario referente, '
    + 'política de seguridad / NDA (sin acuerdo firmado es obligatoria)')),
  { referente: 'Completá este campo', politica_nda: 'Completá este campo' });
  assert.deepEqual(plano(erroresPorCampo('Ya existe el proveedor «ODOO»')), { nombre: 'Ya existe el proveedor «ODOO»' });
  assert.deepEqual(plano(erroresPorCampo('Ya existe un proveedor con ese nombre')), { nombre: 'Ya existe un proveedor con ese nombre' });
  assert.deepEqual(plano(erroresPorCampo('Pagina web: formato de URL inválido; CUIT inválido: el dígito verificador no es correcto')),
    { pagina_web: 'Pagina web: formato de URL inválido', cuit: 'CUIT inválido: el dígito verificador no es correcto' });
  assert.deepEqual(plano(erroresPorCampo('El contenido del archivo no coincide con su extensión')),
    { adjunto: 'El contenido del archivo no coincide con su extensión' });
  assert.deepEqual(plano(erroresPorCampo('Error de comunicación con el servidor')), {});

  const fetch = async () => ({ ok: false, json: async () => ({ detail: 'Pagina web: formato de URL inválido' }) });
  const form = controlador('proveedores_form.html', 'formularioProveedor',
    [{ api: '/api', lista: '/administracion/proveedores' }], { 'proveedor-datos': PROVEEDOR },
    { fetch, window: { scrollTo: () => {} } });
  form.$nextTick = funcion => funcion();
  const web = campoFalso('contacto', { campo: 'pagina_web' });
  form.$refs = { form: formFalso([], { pagina_web: web }) };
  form.tab = 'datos';
  await form.guardar();
  assert.equal(form.tab, 'contacto');
  assert.equal(form.errores.pagina_web, 'Pagina web: formato de URL inválido');
  assert.equal(web.desplazado && web.enfocado, true);
  assert.equal(form.error, null);  // el aviso va debajo del campo
  assert.equal(form.guardando, false);
  // Al editar el campo se le saca la marca
  form.revisar({ target: web });
  assert.equal('pagina_web' in form.errores, false);
});

test('formulario de edición: el estado viaja como activo, solo en la edición', () => {
  const activo = formulario(JSON.stringify({ id: 'p1', nombre: 'ODOO', activo: true }));
  assert.equal(activo.estado, 'activo');
  activo.estado = 'inactivo';
  assert.equal(activo.cuerpo().activo, false);
  assert.equal(activo.estadoGuardado, 'activo');  // para avisar que sale de la evaluación activa
  const inactivo = formulario(JSON.stringify({ id: 'p2', nombre: 'Webmail', activo: false }));
  assert.equal(inactivo.estado, 'inactivo');
  inactivo.estado = 'activo';
  assert.equal(inactivo.cuerpo().activo, true);
  assert.equal('activo' in formulario('{}').cuerpo(), false);  // el alta siempre nace activa
});

test('documentos: miniatura, tipo, tamaño y fecha de cada uno', () => {
  const form = formulario(JSON.stringify({ id: 'p1', nombre: 'ODOO', documentos: [
    { id: 'd1', nombre: 'Contrato.pdf', extension: '.pdf', tamano: 2516582, con_miniatura: true, subido_at: '2026-10-09T12:00:00' },
  ] }));
  const [d] = form.documentos;
  assert.equal(form.urlDocumento(d), '/administracion/proveedores/p1/documentos/d1');
  assert.equal(form.urlMiniatura(d), '/administracion/proveedores/p1/documentos/d1/miniatura');
  assert.equal(form.tipoDocumento(d), 'PDF');
  assert.equal(form.colorDocumento({ extension: '.xlsx' }), 'text-emerald-600');
  assert.equal(form.tamanoLegible(850), '850 B');
  assert.equal(form.tamanoLegible(120 * 1024), '120 KB');
  assert.equal(form.tamanoLegible(d.tamano), '2,4 MB');
  assert.equal(form.fechaCorta(d.subido_at), '09/10/2026');
});

test('documentos: avisa antes de subir lo que la API va a rechazar y sube varios juntos', async () => {
  const pedidos = [];
  const toasts = [];
  const fetch = async (url, opciones) => {
    pedidos.push([url, opciones.method, opciones.body.getAll('archivos').length]);
    return { ok: true, json: async () => [{ id: 'd2', nombre: 'b.xlsx' }, { id: 'd3', nombre: 'c.png' }] };
  };
  const form = controlador('proveedores_form.html', 'formularioProveedor',
    [{ api: '/api', lista: '/administracion/proveedores' }],
    { 'proveedor-datos': JSON.stringify({ id: 'p1', nombre: 'ODOO', documentos: [{ id: 'd1', nombre: 'a.pdf' }] }) },
    { fetch, FormData, Alpine: { store: () => ({ success: texto => toasts.push(texto) }) },
      lucide: { createIcons: () => {} } });
  form.$nextTick = funcion => funcion();
  const archivo = (name, size = 100) => ({ name, size });

  await form.subirDocumentos([archivo('virus.exe')]);
  assert.equal(form.errorDocumentos, '«virus.exe»: solo se aceptan PDF, XLSX, PNG, JPG, DOC o DOCX');
  await form.subirDocumentos([archivo('enorme.pdf', 11 * 1024 * 1024)]);
  assert.equal(form.errorDocumentos, '«enorme.pdf»: supera los 10 MB');
  assert.equal(pedidos.length, 0);

  await form.subirDocumentos([archivo('b.XLSX'), archivo('c.png')]);
  assert.deepEqual(pedidos, [['/administracion/proveedores/p1/documentos', 'POST', 2]]);
  assert.equal(form.errorDocumentos, null);
  assert.deepEqual(plano(form.documentos.map(d => d.id)), ['d2', 'd3', 'd1']);  // los nuevos, primero
  assert.deepEqual(toasts, ['2 documentos subidos']);
  assert.equal(form.subiendoDocumentos, false);
});

test('documentos: eliminar pide confirmación y lo saca de la lista', async () => {
  let confirmado = false;
  const pedidos = [];
  const form = controlador('proveedores_form.html', 'formularioProveedor',
    [{ api: '/api', lista: '/administracion/proveedores' }],
    { 'proveedor-datos': JSON.stringify({ id: 'p1', nombre: 'ODOO', documentos: [{ id: 'd1', nombre: 'a.pdf' }] }) },
    { confirm: () => confirmado, Alpine: { store: () => ({ success: () => {} }) },
      fetch: async (url, opciones) => { pedidos.push([url, opciones.method]); return { ok: true, json: async () => ({}) }; } });
  const [d] = form.documentos;
  await form.eliminarDocumento(d);
  assert.equal(pedidos.length, 0);
  confirmado = true;
  await form.eliminarDocumento(d);
  assert.deepEqual(pedidos, [['/api/p1/documentos/d1', 'DELETE']]);
  assert.deepEqual(plano(form.documentos), []);
});

test('formulario: domicilio legible y elección de referente', () => {
  const form = formulario(PROVEEDOR);
  assert.equal(form.domicilio({ calle: 'Av. Colón', numero: '1200', piso: '3', departamento: 'B',
    localidad: 'Córdoba', provincia: 'Córdoba', pais: 'Argentina', codigo_postal: '5000' }),
  'Av. Colón 1200, piso 3 depto B, Córdoba, Córdoba, Argentina, CP 5000');
  assert.equal(form.domicilio({ calle: 'Calle 1', localidad: 'Hangzhou', pais: 'China' }), 'Calle 1, Hangzhou, China');
  form.elegirReferente({ id: 'e2', nombre: 'Gonzalez, Natalia' });
  assert.equal(form.datos.referente_empleado_id, 'e2');
  assert.equal(form.mostrarEmpleados, false);
});

test('formulario: oficinas y contactos en tabla o cards', () => {
  const form = formulario(PROVEEDOR);
  assert.equal(form.vista, 'tabla');  // sin localStorage (o vacío) arranca en tabla
  const o = { calle: 'Av. Colón', numero: '1200', piso: '3', departamento: 'B', localidad: 'Córdoba', pais: 'Argentina', codigo_postal: '5000' };
  assert.equal(form.direccion(o), 'Av. Colón 1200, piso 3 depto B');
  assert.equal(form.ubicacion(o), 'Córdoba, Argentina, CP 5000');
  assert.equal(form.direccion({ localidad: 'X' }), '');
  assert.equal(form.nombreContacto({ nombre: 'Ana', apellido: 'Pérez' }), 'Ana Pérez');
  assert.equal(form.iniciales({ nombre: 'ana', apellido: 'pérez' }), 'AP');
  assert.equal(form.iniciales({ nombre: 'Soporte' }), 'S');
});

test('formulario: abre en la pestaña pedida, datos fiscales y links a oficina y contacto', () => {
  const form = controlador('proveedores_form.html', 'formularioProveedor',
    [{ api: '/api', lista: '/administracion/proveedores', tab: 'oficinas' }],
    { 'proveedor-datos': JSON.stringify({ id: 'p1', nombre: 'ODOO', cuit: '30-70851936-3', responsabilidad_afip: null }) });
  assert.equal(form.tab, 'oficinas');
  assert.equal(form.datos.cuit, '30-70851936-3');
  assert.equal(form.cuerpo().responsabilidad_afip, null);  // «Sin dato» va como null
  assert.equal(form.urlOficina({ id: 'o1' }), '/administracion/proveedores/p1/oficinas/o1/editar');
  assert.equal(form.urlContacto({ id: 'c1' }), '/administracion/proveedores/p1/contactos/c1/editar');
});

test('página de oficina: vacía para agregar y cargada para editar', () => {
  const nueva = controlador('proveedores_oficina_form.html', 'formularioOficina', [{ url: '/u', volver: '/v' }], { 'oficina-datos': '{}' });
  assert.equal(nueva.id, null);
  assert.deepEqual(plano(nueva.datos), { nombre_oficina: '', calle: '', numero: '', piso: '', departamento: '',
    localidad: '', provincia: '', pais: 'Argentina', codigo_postal: '', es_legal: false });
  const edicion = controlador('proveedores_oficina_form.html', 'formularioOficina', [{ url: '/u', volver: '/v' }],
    { 'oficina-datos': JSON.stringify({ id: 'o1', calle: 'Av. Colón', pais: null, es_legal: true }) });
  assert.equal(edicion.id, 'o1');
  assert.equal(edicion.datos.pais, 'Argentina');
  assert.equal(edicion.datos.es_legal, true);
});

test('página de contacto: la oficina vacía va como null', () => {
  const contacto = controlador('proveedores_contacto_form.html', 'formularioContacto', [{ url: '/u', volver: '/v' }],
    { 'contacto-datos': JSON.stringify({ id: 'c1', nombre: 'Ana', oficina: 'Casa central', oficina_id: null }) });
  assert.equal(contacto.id, 'c1');
  assert.equal(contacto.datos.oficina_id, '');
  assert.equal(contacto.cuerpo().oficina_id, null);
  assert.equal('oficina' in contacto.cuerpo(), false);  // el nombre de la oficina no se manda
  contacto.datos.oficina_id = 'o1';
  assert.equal(contacto.cuerpo().oficina_id, 'o1');
});

test('configuración: eliminar una evaluación explica lo que se pierde y la borra', async () => {
  const pedidos = [];
  const fetch = async (url, opciones = {}) => {
    pedidos.push([url, opciones.method || 'GET']);
    return { ok: true, json: async () => [] };
  };
  const config = controlador('config_evaluaciones_proveedores.html', 'configEvaluaciones', ['/base'], {},
    { fetch, Alpine: { store: () => ({ success: () => {} }) } });
  const vigente = { id: 'e1', periodo: '2026', fecha_apertura: '2026-10-01', fecha_cierre: '2026-10-31',
    estado: 'abierta', metricas: { total: 12, evaluados: 1 } };
  assert.deepEqual(plano(config.textoEliminar(vigente)), [
    'Del 01/10/2026 al 31/10/2026, con 12 proveedores (1 ya evaluado).',
    'Sus respuestas dejan de verse en el tablero y en la ficha de cada proveedor.',
    'Es la evaluación vigente: no va a quedar ninguna hasta que crees otra.',
  ]);
  assert.deepEqual(plano(config.textoEliminar({ ...vigente, estado: 'reemplazada', metricas: { total: 0, evaluados: 0 } })), [
    'Del 01/10/2026 al 31/10/2026, con 0 proveedores.',
    'Sus respuestas dejan de verse en el tablero y en la ficha de cada proveedor.',
  ]);
  assert.deepEqual(plano(config.textoEliminar(null)), []);

  config.porEliminar = vigente;
  config.fechas = { id: 'e1' };
  await config.eliminarEvaluacion();
  assert.deepEqual(plano(pedidos), [['/base/api/evaluaciones/e1', 'DELETE'], ['/base/api/evaluaciones', 'GET']]);
  assert.equal(config.porEliminar, null);
  assert.equal(config.fechas.id, null);
  assert.equal(config.eliminando, false);
});

test('auto-generación: el form carga lo guardado, manda números y explica la próxima', async () => {
  const pedidos = [];
  const guardado = { activa: true, inicio_dia: 1, inicio_mes: 3, fin_dia: 30, fin_mes: 4, ultimo_periodo: '2026',
    proxima: { periodo: '2027', fecha_apertura: '2027-03-01', fecha_cierre: '2027-04-30', ya_existe: false } };
  const fetch = async (url, opciones = {}) => {
    pedidos.push([url, opciones.method || 'GET', opciones.body]);
    return { ok: true, json: async () => guardado };
  };
  const config = controlador('config_evaluaciones_proveedores.html', 'configEvaluaciones', ['/base', 'autogeneracion'], {},
    { fetch, Alpine: { store: () => ({ success: () => {} }) } });
  assert.equal(config.MESES.length, 12);
  assert.equal(config.textoProxima(), '');  // sin cargar todavía
  await config.cargarAutogeneracion();
  assert.deepEqual(plano(config.formAuto), { activa: true, inicio_dia: 1, inicio_mes: 3, fin_dia: 30, fin_mes: 4 });
  assert.equal(config.textoProxima(), 'Próxima: la evaluación 2027 se crea el 01/03/2027 y cierra el 30/04/2027.');

  config.formAuto = { activa: false, inicio_dia: '15', inicio_mes: '', fin_dia: '', fin_mes: 12 };
  assert.deepEqual(plano(config.cuerpoAutogeneracion()),
    { activa: false, inicio_dia: 15, inicio_mes: null, fin_dia: null, fin_mes: 12 });
  await config.guardarAutogeneracion();
  assert.deepEqual(plano(pedidos.map(p => p.slice(0, 2))),
    [['/base/api/autogeneracion', 'GET'], ['/base/api/autogeneracion', 'PUT']]);
  assert.equal(config.guardandoAuto, false);

  config.auto = { ...guardado, proxima: { ...guardado.proxima, ya_existe: true } };
  assert.equal(config.textoProxima(), 'La evaluación 2027 ya existe: este año no se crea otra.');
  config.auto = { ...guardado, activa: false };
  assert.equal(config.textoProxima(), '');
});

test('fuente de datos: el Sheet se carga solo con el link y la hoja guardados', () => {
  const config = controlador('config_evaluaciones_proveedores.html', 'configEvaluaciones', ['/base']);
  config.configuracion = { sheet_url: 'https://docs.google.com/spreadsheets/d/abc', sheet_hoja: 'Listado Proveedores' };
  config.formConfig = { sheet_url: 'https://docs.google.com/spreadsheets/d/abc ', sheet_hoja: 'Listado Proveedores' };
  assert.equal(config.sinGuardar(), false);
  config.formConfig.sheet_hoja = 'Otra hoja';
  assert.equal(config.sinGuardar(), true);
  config.formConfig = { sheet_url: 'https://docs.google.com/spreadsheets/d/otro', sheet_hoja: 'Listado Proveedores' };
  assert.equal(config.sinGuardar(), true);
});

test('importación del Sheet: cambios marcados, textos y cancelación', () => {
  const importar = controlador('config_evaluaciones_importar.html', 'importarSheet', [{ api: '/api', volver: '/volver' }]);
  assert.equal(importar.estado, 'leyendo');
  importar.vista = { id: 'v1', filas: [
    { id: 'a', accion: 'cambio_referente', confirmar: true },
    { id: 'b', accion: 'cambio_referente', confirmar: false },
    { id: 'c', accion: 'alta', confirmar: true },
  ] };
  assert.deepEqual(plano(importar.cambiosConfirmados()), ['a']);  // solo los cambios de referente marcados
  assert.equal(importar.textoAccion('cambio_referente'), 'Cambia el referente');
  assert.equal(importar.claseAccion('alta'), 'bg-emerald-100 text-emerald-700');
});

test('importación del Sheet: dice qué pasa con la evaluación, no solo con el registro', () => {
  const importar = controlador('config_evaluaciones_importar.html', 'importarSheet', [{ api: '/api', volver: '/volver' }]);
  importar.estado = 'vista';
  importar.vista = { id: 'v1', evaluacion: '2026', filas_leidas: 87, se_agregan: 83, ya_estan: 4, de_baja: 0,
    altas: 0, cambios_referente: 1, sin_definir: 3, filas: [] };

  const tarjetas = plano(importar.tarjetas());
  assert.deepEqual(tarjetas[0], { etiqueta: 'Se agregan a la evaluación 2026', valor: 83, destacada: true });
  assert.ok(!tarjetas.some(t => t.etiqueta.startsWith('Inactivos')));  // sin inactivos, no se muestra
  importar.vista.de_baja = 2;
  assert.equal(importar.tarjetas()[2].etiqueta, 'Inactivos (no se agregan)');
  assert.equal(importar.textoConfirmar(), 'Confirmar y agregar 83 a la evaluación 2026');
  assert.equal(importar.textoEvaluacion('ya_esta'), 'Ya está');
  assert.equal(importar.textoEvaluacion('de_baja'), 'Inactivo: no se agrega');

  importar.resultado = { altas: 0, cambios_referente: 1, asignados: 83, ya_estaban: 4 };
  assert.equal(importar.textoResultado(),
    'Evaluación 2026: 83 proveedores agregados (4 ya estaban). En el registro: 0 altas y 1 cambio de referente.');
});

test('config: abre en la pestaña pedida', () => {
  const config = controlador('config_evaluaciones_proveedores.html', 'configEvaluaciones', ['/base', 'fuente']);
  assert.equal(config.pestana, 'fuente');
  assert.equal(controlador('config_evaluaciones_proveedores.html', 'configEvaluaciones', ['/base']).pestana, 'evaluaciones');
});

test('formulario: máscara y dígito verificador del CUIT, como en Clientes', () => {
  const form = formulario(PROVEEDOR);
  assert.equal(form.mascaraCuit('2'), '2');
  assert.equal(form.mascaraCuit('307'), '30-7');
  assert.equal(form.mascaraCuit('3070851936'), '30-70851936');
  assert.equal(form.mascaraCuit('30708519363999'), '30-70851936-3');  // corta en 11 dígitos
  assert.equal(form.mascaraCuit('30-7085a1936-3'), '30-70851936-3');
  const campo = valor => ({ value: valor, mensaje: null, setCustomValidity(m) { this.mensaje = m; }, reportValidity() {} });
  for (const [valor, error] of [['30-70851936-3', ''], ['30-70851936-4', 'dígito verificador'], ['30-708', '11 dígitos'], ['', '']]) {
    const c = campo(valor);
    form.validarCuit(c);
    assert.ok(error ? c.mensaje.includes(error) : c.mensaje === '', `${valor}: ${c.mensaje}`);
  }
});

test('formulario: WhatsApp con código de país y referente como ficha', () => {
  const form = formulario(JSON.stringify({ id: 'p1', nombre: 'ODOO', telefono_whatsapp: '5493511234567',
    referente: { id: 'e1', nombre: 'Vega, Federico' } }));
  // Sin la librería (como acá) queda «+dígitos»; en el navegador la formatea por país
  assert.equal(form.datos.telefono_whatsapp, '+5493511234567');
  assert.equal(form.formatearTelefono('54 9 (351) 123-4567 999 999'), '+549351123456799');  // 15 dígitos como máximo
  assert.equal(form.formatearTelefono(''), '');
  form.datos.telefono_whatsapp = '+54 9 351 123 4567';
  assert.equal(form.cuerpo().telefono_whatsapp, '5493511234567');  // viaja solo con dígitos
  form.datos.telefono_whatsapp = '';
  assert.equal(form.cuerpo().telefono_whatsapp, null);

  form.cambiandoReferente = true;
  form.elegirReferente({ id: 'e2', nombre: 'Gonzalez, Natalia' });
  assert.equal(form.cambiandoReferente, false);
  assert.equal(form.datos.referente_empleado_id, 'e2');
  assert.equal('quitarReferente' in form, false);  // obligatorio: se cambia, no se quita
});

test('canales: la prueba usa los canales de la pantalla y el evaluador elegido', async () => {
  let confirmado = true;
  const config = controlador('config_evaluaciones_proveedores.html', 'configEvaluaciones', ['/base'], {},
    { confirm: () => confirmado });
  config.formConfig = { canal_email: true, email_cc: 'it@dicsys.com', canal_webex_personal: false,
    canal_webex_canal: true, webex_room_id: 'room-1' };
  assert.deepEqual(plano(config.canalesTildados()), ['email', 'webex_canal']);
  config.seguimiento = { evaluadores: [{ evaluador: { id: 'e1', nombre: 'Vega, Federico' }, pendientes: ['ODOO'] }] };
  config.prueba.evaluador = 'e1';
  assert.deepEqual(plano(config.cuerpoPrueba()), { evaluador_id: 'e1', canal_email: true, email_cc: 'it@dicsys.com',
    canal_webex_personal: false, canal_webex_canal: true, webex_room_id: 'room-1' });

  const pedidos = [];
  config.pedir = async (ruta, opciones) => { pedidos.push([ruta, JSON.parse(opciones.body)]); return [{ canal: 'email', enviado: true }]; };
  await config.probarCanales();
  assert.equal(pedidos[0][0], 'seguimiento/probar');
  assert.equal(config.prueba.resultados.length, 1);
  assert.equal(config.prueba.enviando, false);

  confirmado = false;  // si no confirma, no se manda nada
  await config.probarCanales();
  assert.equal(pedidos.length, 1);
});

test('seguimiento: selección de evaluadores con pendientes', () => {
  const config = controlador('config_evaluaciones_proveedores.html', 'configEvaluaciones', ['/base']);
  config.seguimiento = { evaluadores: [
    { evaluador: { id: 'a' }, pendientes: ['ODOO'] },
    { evaluador: { id: 'b' }, pendientes: [] },
    { evaluador: { id: 'c' }, pendientes: ['Webex', 'Claude'] },
  ] };
  assert.deepEqual(plano(config.enviables().map(s => s.evaluador.id)), ['a', 'c']);
  config.alternarTodos();
  assert.deepEqual(plano(config.seleccion), ['a', 'c']);
  assert.equal(config.todosMarcados(), true);
  config.alternar('a');
  assert.deepEqual(plano(config.seleccion), ['c']);
  config.alternarTodos();
  assert.deepEqual(plano(config.seleccion), ['a', 'c']);
  config.alternarTodos();
  assert.deepEqual(plano(config.seleccion), []);
});
