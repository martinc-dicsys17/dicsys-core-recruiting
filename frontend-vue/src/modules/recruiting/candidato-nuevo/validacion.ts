import type { CandidatoCreate, FormularioCandidato } from './types'

/** Validaciones y formatos del formulario Nuevo Candidato (mismas reglas que la pantalla anterior). */

export const ANIO_NACIMIENTO_MIN = 1900
export const ANIO_NACIMIENTO_MAX = 2010
export const TAMANO_MAX_CV = 2 * 1024 * 1024
export const EXTENSIONES_CV = ['pdf', 'doc', 'docx']

const RE_EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
const RE_UUID = /^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i

export function emailValido(texto: string): boolean {
  return RE_EMAIL.test(texto.trim())
}

/** El teléfono admite solo dígitos y «+». */
export function limpiarTelefono(texto: string): string {
  return texto.replace(/[^0-9+]/g, '')
}

/** Máscara DD-MM-AAAA: deja solo dígitos (hasta 8) y agrega los guiones. */
export function enmascararFecha(texto: string): string {
  const digitos = texto.replace(/\D/g, '').slice(0, 8)
  let salida = digitos.slice(0, 2)
  if (digitos.length > 2) salida += `-${digitos.slice(2, 4)}`
  if (digitos.length > 4) salida += `-${digitos.slice(4, 8)}`
  return salida
}

interface PartesFecha {
  dia: number
  mes: number
  anio: number
}

function partesDeFecha(texto: string): PartesFecha | null {
  const dmy = /^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$/.exec(texto)
  if (dmy) return { dia: Number(dmy[1]), mes: Number(dmy[2]), anio: Number(dmy[3]) }
  const ymd = /^(\d{4})[/-](\d{1,2})[/-](\d{1,2})$/.exec(texto)
  if (ymd) return { anio: Number(ymd[1]), mes: Number(ymd[2]), dia: Number(ymd[3]) }
  return null
}

/** Mensaje de error de la fecha de nacimiento, o '' si está vacía o es válida. */
export function errorFechaNacimiento(texto: string): string {
  const valor = texto.trim()
  if (!valor) return ''
  const partes = partesDeFecha(valor)
  if (!partes || partes.mes < 1 || partes.mes > 12) return 'Fecha inválida'
  if (partes.anio < ANIO_NACIMIENTO_MIN || partes.anio > ANIO_NACIMIENTO_MAX) {
    return `El año de nacimiento debe estar entre ${ANIO_NACIMIENTO_MIN} y ${ANIO_NACIMIENTO_MAX}`
  }
  const fecha = new Date(partes.anio, partes.mes - 1, partes.dia)
  const existe =
    fecha.getFullYear() === partes.anio && fecha.getMonth() === partes.mes - 1 && fecha.getDate() === partes.dia
  return existe ? '' : 'Fecha inválida'
}

/** Fecha en el formato que espera el backend (AAAA-MM-DD), o null si está vacía. */
export function fechaAIso(texto: string): string | null {
  const partes = partesDeFecha(texto.trim())
  if (!partes) return null
  const dos = (n: number) => String(n).padStart(2, '0')
  return `${partes.anio}-${dos(partes.mes)}-${dos(partes.dia)}`
}

/** Mensaje de error de un archivo de CV (formato y tamaño), o '' si es válido. */
export function errorArchivoCv(archivo: { name: string; size: number }): string {
  const punto = archivo.name.lastIndexOf('.')
  const extension = punto >= 0 ? archivo.name.slice(punto + 1).toLowerCase() : ''
  if (!EXTENSIONES_CV.includes(extension)) return 'Formato inválido. Solo se admiten archivos PDF, DOC o DOCX.'
  if (archivo.size > TAMANO_MAX_CV) return 'El archivo supera el tamaño máximo permitido de 2 MB.'
  return ''
}

export function tamanoLegible(bytes: number): string {
  return bytes < 1024 * 1024 ? `${(bytes / 1024).toFixed(0)} KB` : `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

/** Id de búsqueda válido (UUID) o ''. */
export function busquedaIdValido(valor: unknown): string {
  const texto = typeof valor === 'string' ? valor.trim() : ''
  return RE_UUID.test(texto) ? texto : ''
}

/**
 * Destino de «Volver» y de después de guardar: solo rutas internas de Recruiting (misma regla que
 * `_volver_valido` en frontend/modulos/recruiting/app_module.py). Sin «volver» válido: la búsqueda de
 * origen, si hay, o el listado de candidatos.
 */
export function destinoVolver(volver: unknown, busquedaId: string): string {
  const porDefecto = busquedaId ? `/recruiting/oportunidades/${busquedaId}` : '/recruiting/candidatos'
  if (typeof volver !== 'string') return porDefecto
  const destino = volver.trim()
  const hayControl = [...destino].some((c) => c.charCodeAt(0) < 32)
  if (!destino || destino.length > 1000 || destino.startsWith('//') || destino.includes('\\') || hayControl) {
    return porDefecto
  }
  const ruta = destino.split(/[?#]/)[0] ?? ''
  if (ruta !== '/recruiting' && !ruta.startsWith('/recruiting/')) return porDefecto
  let decodificada: string
  try {
    decodificada = decodeURIComponent(ruta)
  } catch {
    return porDefecto
  }
  return decodificada.split('/').includes('..') ? porDefecto : destino
}

const vacioANulo = (texto: string | null): string | null => texto?.trim() || null

/** Arma el cuerpo de CandidatoCreate igual que lo hacía la pantalla anterior (`_payload_de_candidato`). */
export function armarAlta(f: FormularioCandidato): CandidatoCreate {
  return {
    nombre: f.nombre.trim(),
    apellido: f.apellido.trim(),
    email: f.email.trim(),
    telefono: vacioANulo(f.telefono),
    provincia_id: f.provincia_id,
    ciudad_id: f.ciudad_id,
    dni: vacioANulo(f.dni),
    fecha_nacimiento: fechaAIso(f.fecha_nacimiento),
    linkedin_url: vacioANulo(f.linkedin),
    headline: vacioANulo(f.puesto),
    seniority: vacioANulo(f.seniority),
    modalidad: vacioANulo(f.modalidad),
    skills: f.skills,
    habilidades: f.habilidades,
    pretension_salarial: null,
    moneda_pretension: 'ARS',
    estado: 'Activo',
    fuente: 'Portal Propio',
  }
}
