import {
  AlertTriangle,
  CheckCircle,
  Circle,
  Copy,
  Folder,
  Slash,
  XCircle,
  type LucideIcon,
} from '@lucide/vue'

/** Presentación de cada carpeta de CV (las claves reales las define el backend). */
export interface MetaCarpeta {
  titulo: string
  detalle: string
  icono: LucideIcon
  tarjeta: string
  activa: string
  icono_caja: string
  cifra: string
  boton: string
}

const META: Record<string, MetaCarpeta> = {
  cv_procesados_ok: {
    titulo: 'Procesados correctamente',
    detalle: 'CV importados correctamente',
    icono: CheckCircle,
    tarjeta: 'border-emerald-200 bg-emerald-50/40 hover:border-emerald-300',
    activa: 'border-emerald-500 ring-2 ring-emerald-500/20 bg-emerald-50',
    icono_caja: 'bg-emerald-100 text-emerald-600',
    cifra: 'text-emerald-700',
    boton: 'bg-emerald-600 hover:bg-emerald-700',
  },
  cv_duplicados: {
    titulo: 'Duplicados',
    detalle: 'CV de candidatos que ya existen',
    icono: Copy,
    tarjeta: 'border-amber-200 bg-amber-50/40 hover:border-amber-300',
    activa: 'border-amber-500 ring-2 ring-amber-500/20 bg-amber-50',
    icono_caja: 'bg-amber-100 text-amber-600',
    cifra: 'text-amber-700',
    boton: 'bg-amber-600 hover:bg-amber-700',
  },
  cv_errores: {
    titulo: 'Con errores',
    detalle: 'CV rechazados por error de lectura o procesamiento',
    icono: AlertTriangle,
    tarjeta: 'border-rose-200 bg-rose-50/40 hover:border-rose-300',
    activa: 'border-rose-500 ring-2 ring-rose-500/20 bg-rose-50',
    icono_caja: 'bg-rose-100 text-rose-600',
    cifra: 'text-rose-700',
    boton: 'bg-rose-600 hover:bg-rose-700',
  },
}

const META_DEFECTO: MetaCarpeta = {
  titulo: 'Carpeta',
  detalle: '',
  icono: Folder,
  tarjeta: 'border-dark-200 bg-white hover:border-dark-300',
  activa: 'border-primary-500 ring-2 ring-primary-500/20 bg-primary-50',
  icono_caja: 'bg-dark-100 text-dark-600',
  cifra: 'text-dark-700',
  boton: 'bg-primary-600 hover:bg-primary-700',
}

export function metaCarpeta(carpeta: string): MetaCarpeta {
  return META[carpeta] ?? META_DEFECTO
}

/** Resultado de una operación de carga (badge con color e icono). */
export const RESULTADOS_CARGA: Record<string, { texto: string; clase: string; icono: LucideIcon }> = {
  completada: { texto: 'Completada', clase: 'bg-emerald-50 text-emerald-700 border-emerald-200', icono: CheckCircle },
  parcial: { texto: 'Parcial', clase: 'bg-amber-50 text-amber-700 border-amber-200', icono: AlertTriangle },
  fallida: { texto: 'Fallida', clase: 'bg-rose-50 text-rose-700 border-rose-200', icono: XCircle },
  cancelada: { texto: 'Cancelada', clase: 'bg-dark-100 text-dark-600 border-dark-200', icono: Slash },
}

export function resultadoCarga(resultado: string) {
  return RESULTADOS_CARGA[resultado] ?? { texto: resultado, clase: 'bg-dark-100 text-dark-600 border-dark-200', icono: Circle }
}

/** Resultado de cada archivo dentro de una operación de carga. */
export const RESULTADOS_ARCHIVO: Record<string, { texto: string; clase: string }> = {
  creado: { texto: 'Creado', clase: 'bg-emerald-50 text-emerald-700 border-emerald-200' },
  duplicado: { texto: 'Duplicado', clase: 'bg-amber-50 text-amber-700 border-amber-200' },
  sin_email: { texto: 'Sin email', clase: 'bg-orange-50 text-orange-700 border-orange-200' },
  rechazado: { texto: 'Rechazado', clase: 'bg-rose-50 text-rose-700 border-rose-200' },
}

export function resultadoArchivo(resultado: string) {
  return RESULTADOS_ARCHIVO[resultado] ?? { texto: resultado, clase: 'bg-dark-100 text-dark-600 border-dark-200' }
}

const ETIQUETAS_REGISTRO: Record<string, string> = {
  recruiting_candidatos: 'Candidatos',
  recruiting_oportunidades: 'Búsquedas',
  recruiting_postulaciones: 'Postulaciones',
  recruiting_gestionBusqueda: 'Gestión del pipeline',
  recruiting_historial_pipeline: 'Historial del pipeline',
  recruiting_transiciones_estado: 'Transiciones de estado',
  recruiting_etapa_archivos: 'Adjuntos de etapas',
  recruiting_candidatos_duplicados: 'Casos de CV duplicado',
  core_notificaciones_internas: 'Notificaciones de Recruiting',
}

export function etiquetaRegistro(clave: string): string {
  return ETIQUETAS_REGISTRO[clave] ?? clave
}

const ETIQUETAS_ARCHIVO: Record<string, string> = {
  cv_candidatos: 'CV vinculados a candidatos',
  adjuntos_etapas: 'Adjuntos de etapas',
  cv_duplicados_pendientes: 'CV de duplicados pendientes',
  cv_procesados_ok: 'Carpeta cv_procesados_ok',
  cv_duplicados: 'Carpeta cv_duplicados',
  cv_errores: 'Carpeta cv_errores',
}

export function etiquetaArchivo(clave: string): string {
  return ETIQUETAS_ARCHIVO[clave] ?? clave
}

/** Fecha y hora como en la interfaz anterior (es-AR, con segundos). */
export function formatearFechaHora(iso: string): string {
  const fecha = new Date(iso)
  if (Number.isNaN(fecha.getTime())) return '-'
  return fecha.toLocaleString('es-AR', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

/** Fecha del historial: el backend manda la hora sin zona; se interpreta como UTC igual que antes. */
export function formatearFechaHistorial(valor: string | null | undefined): string {
  if (!valor) return '-'
  const fecha = new Date(/(Z|[+-]\d\d:?\d\d)$/.test(valor) ? valor : `${valor}Z`)
  return Number.isNaN(fecha.getTime()) ? valor : fecha.toLocaleString('es-AR', { dateStyle: 'short', timeStyle: 'short' })
}

export function textoTipoCarga(tipo: string): string {
  if (tipo === 'masiva') return 'Masiva'
  if (tipo === 'individual') return 'Individual'
  return tipo
}
