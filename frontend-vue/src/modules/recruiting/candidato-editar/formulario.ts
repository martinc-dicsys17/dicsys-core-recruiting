import { valoresFicha } from '../candidato-detalle/presentacion.ts'
import type { CandidatoDetalle } from '../candidato-detalle/types'
import { fechaAIso } from '../candidato-nuevo/validacion.ts'
import type { ActualizacionCandidato, FormularioEdicion } from './types'

/** Reglas del formulario de edición: las mismas que la ficha anterior (`sincronizarFormulario` y `guardarCambios`). */

export const MENSAJE_OBLIGATORIOS = 'El nombre, apellido, email y teléfono son obligatorios.'
export const MENSAJE_ACTUALIZADO = 'Ficha del candidato actualizada correctamente.'
export const MENSAJE_ERROR_ACTUALIZAR = 'Ocurrió un error al actualizar los datos.'
export const MENSAJE_SIN_CONEXION = 'Error de conexión con el servidor.'

const comoMoneda = (d: CandidatoDetalle): 'ARS' | 'USD' =>
  (d.moneda || d.moneda_pretension || 'ARS').toUpperCase() === 'USD' ? 'USD' : 'ARS'

/** Monto con separador de miles (es-AR): deja solo dígitos; vacío si no hay ninguno. */
export function formatearSalario(texto: string): string {
  const digitos = texto.replace(/\D/g, '')
  return digitos ? Number(digitos).toLocaleString('es-AR') : ''
}

export function prefijoMoneda(moneda: string): string {
  return moneda === 'USD' ? 'US$' : '$'
}

/** D-M-AAAA o DD/MM/AAAA -> DD-MM-AAAA (al salir del campo); cualquier otro texto queda como está. */
export function normalizarFechaAlSalir(texto: string): string {
  const m = /^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$/.exec(texto.trim())
  return m ? `${m[1]!.padStart(2, '0')}-${m[2]!.padStart(2, '0')}-${m[3]}` : texto
}

/** Valores iniciales del formulario a partir del candidato; provincia y ciudad ya resueltas contra los catálogos. */
export function formularioInicial(
  d: CandidatoDetalle,
  provinciaId: number | null,
  ciudadId: number | null,
): FormularioEdicion {
  const v = valoresFicha(d)
  const monto = d.pretension_salarial ? Number(d.pretension_salarial) : 0
  return {
    nombre: v.nombre,
    apellido: v.apellido,
    email: v.email,
    telefono: v.telefono,
    provincia_id: provinciaId ? String(provinciaId) : '',
    ciudad_id: ciudadId ? String(ciudadId) : '',
    dni: v.dni,
    fecha_nacimiento: v.fechaNacimiento,
    estado: v.estado,
    headline: v.headline,
    seniority: v.seniority,
    modalidad: v.modalidad,
    salario: monto ? monto.toLocaleString('es-AR') : '',
    moneda: comoMoneda(d),
    fuente: v.fuente,
    linkedin_url: v.linkedin,
    disponibilidad: v.disponibilidad,
    observaciones: v.observaciones,
    skills: [...v.skills],
    habilidades: [...v.habilidades],
  }
}

const vacioANulo = (texto: string): string | null => texto.trim() || null

/** Arma el cuerpo del PUT igual que `guardarCambios` de la ficha anterior. */
export function armarActualizacion(f: FormularioEdicion, ubicacionModificada: boolean): ActualizacionCandidato {
  const salario = f.salario.replace(/[^0-9]/g, '')
  return {
    nombre: f.nombre.trim(),
    apellido: f.apellido.trim(),
    email: f.email.trim(),
    telefono: vacioANulo(f.telefono),
    // Provincia y ciudad solo se envían si se modificaron; el backend arma el texto de ubicación.
    ...(ubicacionModificada
      ? {
          provincia_id: f.provincia_id ? Number(f.provincia_id) : null,
          ciudad_id: f.ciudad_id ? Number(f.ciudad_id) : null,
        }
      : {}),
    dni: vacioANulo(f.dni),
    fecha_nacimiento: fechaAIso(f.fecha_nacimiento) ?? (f.fecha_nacimiento.trim() || null),
    estado: f.estado,
    headline: f.headline.trim(),
    seniority: f.seniority || null,
    modalidad: f.modalidad || null,
    pretension_salarial: salario ? Number.parseFloat(salario) : null,
    moneda: f.moneda || 'ARS',
    moneda_pretension: f.moneda || 'ARS',
    fuente: f.fuente.trim() || 'Portal Propio',
    linkedin_url: vacioANulo(f.linkedin_url),
    disponibilidad: f.disponibilidad || null,
    observaciones: f.observaciones ? f.observaciones.trim() : null,
    skills: f.skills,
    habilidades: f.habilidades,
  }
}
