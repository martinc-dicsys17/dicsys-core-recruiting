/**
 * Personalización de PrimeVue para que la grilla se vea como la pantalla anterior (candidatos.html): mismas clases de
 * Tailwind sobre los componentes, sin el aspecto por defecto del tema. Las variantes `dark:` son por media query, igual
 * que en la pantalla anterior.
 */

/** Combos de la barra de filtros: como el <select> anterior (px-3 py-2 text-sm, fondo dark-50, borde dark-200). */
export const PT_SELECT_FILTRO = {
  // Deshabilitado (skills sin categoría): atenuado y sin cursor de acción, como el <select> anterior.
  root: ({ props }: { props: { disabled?: boolean } }) => ({
    class: [
      'w-full rounded-xl border-dark-200 bg-dark-50 shadow-none transition-colors focus-within:border-primary-500 focus-within:ring-2 focus-within:ring-primary-500/20',
      props.disabled && 'cursor-not-allowed opacity-60',
    ],
  }),
  label: { class: 'px-3 py-2 text-sm leading-5 text-dark-700' },
  dropdown: { class: 'w-8 text-dark-500' },
  dropdownIcon: { class: 'h-3.5 w-3.5' },
}

/** Selector «Mostrar por página»: como el <select> del pie anterior (px-2.5 py-1 text-xs font-semibold). */
export const PT_SELECT_PAGINACION = {
  root: {
    class:
      'rounded-lg border-dark-200 bg-white shadow-2xs dark:border-slate-700 dark:bg-slate-800',
  },
  label: { class: 'px-2.5 py-1 text-xs leading-4 font-semibold text-dark-800 dark:text-slate-100' },
  dropdown: { class: 'w-6 text-dark-500' },
  dropdownIcon: { class: 'h-3 w-3' },
}

/** Buscador: pl-10 pr-4 py-2 text-sm, fondo dark-50, y blanco al enfocar. */
export const CLASE_BUSCADOR =
  'w-full rounded-xl border border-dark-200 bg-dark-50 py-2 pr-4 pl-10 text-sm leading-5 shadow-none outline-none transition-all focus:border-primary-500 focus:bg-white focus:ring-2 focus:ring-primary-500/20'

/** Botones «Anterior» y «Siguiente» del pie. */
export const CLASE_BOTON_PAGINA =
  'inline-flex cursor-pointer items-center gap-1 rounded-lg border border-dark-200 bg-white px-3 py-1.5 text-xs font-medium text-dark-700 shadow-2xs transition-colors hover:bg-dark-50 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-white dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700 dark:disabled:text-slate-500 dark:disabled:hover:bg-slate-800'

/** Botón «Limpiar Filtros». */
export const CLASE_BOTON_LIMPIAR =
  'inline-flex cursor-pointer items-center gap-1.5 rounded-xl border border-dark-200 bg-dark-50 px-3.5 py-2 text-xs font-medium whitespace-nowrap text-dark-600 transition-colors hover:bg-dark-100 hover:text-dark-900'

/** Encabezado de la tabla: gris claro (bg-slate-100) y oscuro cuando el sistema está en modo oscuro. */
export const CLASE_ENCABEZADO =
  'px-4 py-3 text-left text-xs font-semibold tracking-wider text-slate-600 uppercase bg-slate-100 border-b border-slate-200 dark:bg-slate-900/90 dark:text-slate-200 dark:border-slate-700/80'

/** Ventanas (modales): tarjeta redondeada con borde y sombra, fondo oscuro (sin desenfoque, como antes) y encabezado con divisoria. */
export const PT_DIALOGO = {
  mask: { class: 'bg-dark-900/60!' },
  root: { class: 'rounded-2xl border border-dark-100 bg-white shadow-2xl' },
  header: { class: 'mx-6 mt-6 mb-0 border-b border-dark-100 p-0 pb-3' },
  content: { class: 'px-6 pt-4 pb-0' },
  footer: { class: 'gap-3 px-6 pt-6 pb-6' },
  pcCloseButton: {
    root: {
      class:
        'h-auto w-auto rounded-lg border-0 bg-transparent p-1.5 text-dark-400 shadow-none outline-0 hover:bg-dark-50 hover:text-dark-600 focus:shadow-none focus-visible:outline-0',
    },
    icon: { class: 'h-4 w-4' },
  },
}

const BOTON_PIE = 'inline-flex cursor-pointer items-center gap-2 rounded-xl px-4 py-2 text-xs font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-50'
/** Botones del pie de los modales (mismas clases que la pantalla anterior). */
export const CLASE_BOTON_CANCELAR = `${BOTON_PIE} border border-dark-200 bg-white text-dark-600 hover:text-dark-800`
export const CLASE_BOTON_PRIMARIO = `${BOTON_PIE} bg-primary-600 text-white shadow-soft hover:bg-primary-700`
export const CLASE_BOTON_CONFIRMAR = `${BOTON_PIE} bg-emerald-600 text-white shadow-soft hover:bg-emerald-700`
export const CLASE_BOTON_PELIGRO = `${BOTON_PIE} bg-red-600 text-white shadow-soft hover:bg-red-700`
