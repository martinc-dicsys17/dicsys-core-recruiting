import { ErrorApi } from '../../candidato-nuevo/api/candidatos.repository'
import { MENSAJE_CANDIDATO_NO_DISPONIBLE } from '../presentacion'
import type { CandidatoDetalle } from '../types'

/**
 * Datos de la ficha: el candidato sale del backend real por el proxy /api/v1 de Flask (que agrega el token de la
 * sesión). Los catálogos de ubicación y perfiles de puesto se piden con el repositorio de Nuevo Candidato.
 */
export async function obtenerCandidato(id: string): Promise<CandidatoDetalle> {
  let respuesta: Response
  try {
    respuesta = await fetch(`/api/v1/recruiting/candidatos/${id}`, { headers: { Accept: 'application/json' } })
  } catch {
    throw new ErrorApi('Error de conexión con el servidor. Reintentá en unos momentos.', 0)
  }
  let cuerpo: unknown = null
  try {
    cuerpo = await respuesta.json()
  } catch {
    // cuerpo vacío o que no es JSON
  }
  if (!respuesta.ok || !cuerpo || typeof cuerpo !== 'object') {
    const detalle = (cuerpo as { detail?: unknown } | null)?.detail
    throw new ErrorApi(
      typeof detalle === 'string' && detalle ? detalle : MENSAJE_CANDIDATO_NO_DISPONIBLE,
      respuesta.status,
    )
  }
  return cuerpo as CandidatoDetalle
}
