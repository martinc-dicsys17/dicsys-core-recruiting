// node --test frontend/tests/licencias_fecha_check.cjs
const assert = require('node:assert/strict');
const { test } = require('node:test');
const vm = require('node:vm');
const { cargarScript } = require('./licencias_test_source.cjs');

function calendario(inicial) {
  let iconos = 0;
  class FechaFija extends Date {
    constructor(...args) { super(...(args.length ? args : [2026, 8, 6, 12])); }
  }
  const contexto = vm.createContext({ Date: FechaFija, lucide: { createIcons: () => iconos++ } });
  cargarScript('licencias_form.html', contexto);
  const estado = contexto.datepicker(inicial);
  estado.init();
  return { estado, iconos: () => iconos };
}

test('fecha inicial vacía, dd/mm/yyyy y formato inesperado', () => {
  const vacio = calendario().estado;
  assert.equal(vacio.displayValue, '');
  assert.equal(vacio.selectedDate, null);
  assert.equal(vacio.month, 8);
  assert.equal(vacio.year, 2026);
  assert.equal(vacio.isSelected(6), false);
  const existente = calendario('29/02/2024').estado;
  assert.equal(existente.displayValue, '29/02/2024');
  assert.equal(existente.month, 1);
  assert.equal(existente.year, 2024);
  assert.equal(existente.daysInMonth, 29);
  assert.equal(existente.isSelected(29), true);
  const otroFormato = calendario('2026-09-06').estado;
  assert.equal(otroFormato.selectedDate, null);
  assert.equal(otroFormato.displayValue, '2026-09-06');
});

test('calendario comienza lunes y navega entre meses y años', () => {
  const { estado } = calendario('01/03/2026');
  assert.equal(estado.firstDayOfMonth, 6); // Domingo al final de la semana.
  assert.equal(estado.daysInMonth, 31);
  estado.prevMonth();
  assert.equal(estado.month, 1);
  assert.equal(estado.daysInMonth, 28);
  estado.nextMonth();
  assert.equal(estado.month, 2);
  estado.month = 0;
  estado.prevMonth();
  assert.equal(estado.month, 11);
  assert.equal(estado.year, 2025);
  assert.equal(estado.firstDayOfMonth, 0); // 1/12/2025, lunes.
  estado.nextMonth();
  assert.equal(estado.month, 0);
  assert.equal(estado.year, 2026);
});

test('selección distingue día, mes y año; Hoy y Limpiar cierran el selector', () => {
  const { estado, iconos } = calendario('01/01/2024');
  assert.equal(estado.isSelected(2), false);
  estado.month = 1;
  assert.equal(estado.isSelected(1), false);
  estado.month = 0;
  estado.year = 2025;
  assert.equal(estado.isSelected(1), false);
  estado.month = 10;
  estado.open = true;
  estado.selectDate(21);
  assert.equal(estado.displayValue, '21/11/2025');
  assert.equal(estado.isSelected(21), true);
  assert.equal(estado.open, false);
  assert.equal(iconos(), 1);
  estado.open = true;
  estado.setToday();
  assert.equal(estado.displayValue, '06/09/2026');
  assert.equal(estado.month, 8);
  assert.equal(estado.year, 2026);
  assert.equal(estado.open, false);
  assert.equal(iconos(), 2);
  estado.open = true;
  estado.clear();
  assert.equal(estado.displayValue, '');
  assert.equal(estado.selectedDate, null);
  assert.equal(estado.open, false);
});
