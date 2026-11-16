import { candidatosRepository } from '../../candidato-nuevo/api/candidatos.repository'
import { MENSAJE_ERROR_ACTUALIZAR, MENSAJE_SIN_CONEXION } from '../formulario'
import type { ActualizacionCandidato } from '../types'

/** Error al guardar, con el mensaje que se le muestra a la persona. */
export class ErrorActualizar extends Error {}

interface RespuestaActualizar {
  success?: boolean
  error?: string
  detail?: string
}

/**
 * Guarda los datos del candidato con la ruta de Flask que ya usaba la ficha anterior (PUT /recruiting/candidatos/<id>:
 * normaliza la fecha y reenvía al backend). Responde {success, candidato} o {success: false, error}.
 */
export async function actualizarCandidato(id: string, datos: ActualizacionCandidato): Promise<void> {
  let respuesta: Response
  let cuerpo: RespuestaActualizar
  try {
    respuesta = await fetch(`/recruiting/candidatos/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify(datos),
    })
    cuerpo = (await respuesta.json()) as RespuestaActualizar
  } catch {
    throw new ErrorActualizar(MENSAJE_SIN_CONEXION)
  }
  if (!respuesta.ok || !cuerpo.success) {
    throw new ErrorActualizar(cuerpo.error || cuerpo.detail || MENSAJE_ERROR_ACTUALIZAR)
  }
}

/** Reemplaza el CV (ruta de Flask, multipart). Como antes, si falla no se avisa: los datos ya quedaron guardados. */
export async function reemplazarCv(id: string, archivo: File): Promise<void> {
  try {
    await candidatosRepository.subirCv(id, archivo)
  } catch (error) {
    console.error('Error al subir el CV en edición:', error)
  }
}
