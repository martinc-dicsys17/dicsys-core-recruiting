import type { Ciudad, Provincia } from '../candidato-nuevo/types'
import type { CandidatoDetalle } from './types'

/** Reglas de presentación de la ficha: las mismas que la pantalla anterior (candidato_detalle.html). */

export const SENIORITY = ['Trainee', 'Junior', 'Semi Senior', 'Senior', 'Líder Técnico', 'Arquitecto']
export const MODALIDADES = ['Remoto', 'Híbrido', 'Presencial']
export const DISPONIBILIDADES = [
  { valor: 'Inmediata', etiqueta: 'Inmediata' },
  { valor: '2 semanas', etiqueta: '2 semanas (preaviso estándar)' },
  { valor: '1 mes', etiqueta: '1 mes' },
  { valor: 'A convenir', etiqueta: 'A convenir' },
]

export const MENSAJE_CANDIDATO_NO_DISPONIBLE =
  'No se pudo encontrar el candidato solicitado o no tenés permisos para acceder.'

/** Comparación sin tildes ni mayúsculas. */
export function claveUbicacion(texto: string | null | undefined): string {
  return (texto ?? '')
    .normalize('NFD')
    .replace(/\p{Diacritic}/gu, '')
    .toLowerCase()
    .trim()
}

/** Valores de la ficha, con los mismos valores por defecto que la pantalla anterior. */
export interface ValoresFicha {
  nombre: string
  apellido: string
  email: string
  telefono: string
  dni: string
  fechaNacimiento: string
  estado: string
  headline: string
  seniority: string
  modalidad: string
  fuente: string
  linkedin: string
  disponibilidad: string
  observaciones: string
  skills: string[]
  habilidades: string[]
}

/** AAAA-MM-DD -> DD-MM-AAAA; otro formato se muestra tal cual; vacío, vacío. */
export function formatoFechaNacimiento(fecha: string | null | undefined): string {
  if (!fecha) return ''
  const partes = fecha.split('-')
  return partes.length === 3 ? `${partes[2]}-${partes[1]}-${partes[0]}` : fecha
}

export function valoresFicha(d: CandidatoDetalle): ValoresFicha {
  return {
    nombre: d.nombre || '',
    apellido: d.apellido || '',
    email: d.email || '',
    telefono: d.telefono || '',
    dni: d.dni || '',
    fechaNacimiento: formatoFechaNacimiento(d.fecha_nacimiento),
    estado: d.estado || 'Activo',
    headline: d.headline || '',
    seniority: d.seniority || 'Semi Senior',
    modalidad: d.modalidad || 'Remoto',
    fuente: d.fuente || 'Portal Propio',
    linkedin: d.linkedin_url || '',
    disponibilidad: d.disponibilidad || 'Inmediata',
    observaciones: d.observaciones || '',
    skills: Array.isArray(d.skills) ? d.skills : [],
    habilidades: Array.isArray(d.habilidades) ? d.habilidades : [],
  }
}

/** Pretensión salarial como se lee en la ficha: «$ 1.500.000 ARS», «US$ 3.000 USD» o «-». */
export function formatoSalarioLectura(d: CandidatoDetalle): string {
  const monto = Number.parseFloat(String(d.pretension_salarial ?? ''))
  if (!monto || Number.isNaN(monto) || monto <= 0) return '-'
  const moneda = (d.moneda || d.moneda_pretension || 'ARS').toUpperCase()
  const texto = Number(monto).toLocaleString('es-AR')
  return moneda === 'USD' ? `US$ ${texto} USD` : `$ ${texto} ARS`
}

/** Color del estado del encabezado; los estados que no figuran no llevan color propio (como antes). */
export function claseEstado(estado: string | null | undefined): string {
  switch (estado) {
    case 'Activo':
      return 'bg-emerald-100 text-emerald-700'
    case 'Rechazado':
      return 'bg-red-100 text-red-700'
    case 'Baja del proceso':
      return 'bg-dark-100 text-dark-600'
    case 'Sin respuesta':
      return 'bg-amber-100 text-amber-700'
    default:
      return ''
  }
}

/** Nombre del archivo del CV: el último tramo del cv_url, o «Nombre_Apellido_CV». */
export function nombreCv(d: CandidatoDetalle): string {
  if (d.cv_url) {
    const archivo = d.cv_url.split('/').at(-1)
    return archivo || `${d.nombre}_${d.apellido ?? ''}_CV`
  }
  return `${d.nombre || 'Candidato'}_${d.apellido || ''}_CV`
}

const partesDeUbicacion = (d: CandidatoDetalle): string[] =>
  (d.ubicacion ?? '')
    .split(',')
    .map((p) => p.trim())
    .filter(Boolean)

/** Provincia que muestra la ficha: la guardada o, en candidatos anteriores, la que dice el texto «Ciudad, Provincia». */
export function provinciaInicial(d: CandidatoDetalle, provincias: Provincia[]): number | null {
  if (d.provincia_id) return d.provincia_id
  const ultima = partesDeUbicacion(d).at(-1)
  if (!ultima) return null
  const nombre = claveUbicacion(ultima)
  return provincias.find((p) => claveUbicacion(p.nombre) === nombre)?.provincia_id ?? null
}

/** Ciudad que muestra la ficha: la guardada o, en candidatos anteriores, la que dice el texto. */
export function ciudadInicial(d: CandidatoDetalle, provinciaId: number | null, ciudades: Ciudad[]): number | null {
  if (!provinciaId) return null
  if (d.provincia_id) return d.ciudad_id ?? null
  const partes = partesDeUbicacion(d)
  if (partes.length < 2) return null
  const nombre = claveUbicacion(partes[0])
  return ciudades.find((c) => c.provincia_id === provinciaId && claveUbicacion(c.nombre) === nombre)?.ciudad_id ?? null
}

/** «Ciudad, Provincia» según el catálogo y los ids guardados (vacío si no hay provincia guardada). */
export function ubicacionSegunCatalogo(d: CandidatoDetalle, provincias: Provincia[], ciudades: Ciudad[]): string {
  const provincia = provincias.find((p) => String(p.provincia_id) === String(d.provincia_id))
  if (!provincia) return ''
  const ciudad = ciudades.find((c) => String(c.ciudad_id) === String(d.ciudad_id))
  return ciudad ? `${ciudad.nombre}, ${provincia.nombre}` : provincia.nombre
}

/** La ubicación registrada se muestra aparte solo si dice algo distinto del catálogo. */
export function mostrarUbicacionRegistrada(d: CandidatoDetalle, segunCatalogo: string): boolean {
  return Boolean(d.ubicacion) && claveUbicacion(d.ubicacion) !== claveUbicacion(segunCatalogo)
}
