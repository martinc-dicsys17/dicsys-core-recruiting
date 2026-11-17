import { ErrorApi, irAlLoginSiSesionVencida } from '../../candidato-nuevo/api/candidatos.repository'
import type { Busqueda, ExternoDisponible, PaginaBusquedas, PermisosBusquedas } from '../types'

/** Acceso a datos del listado de Búsquedas: todo va al backend real por el proxy /api/v1 de Flask. */
const API = '/api/v1/recruiting'

export { ErrorApi }

async function pedir<T>(ruta: string, opciones: RequestInit, porDefecto: string): Promise<T> {
  let respuesta: Response
  try {
    respuesta = await fetch(ruta, {
      ...opciones,
      headers: { Accept: 'application/json', ...opciones.headers },
    })
  } catch {
    throw new ErrorApi('Error de conexión con el servidor. Reintentá en unos momentos.', 0)
  }
  irAlLoginSiSesionVencida(respuesta.status)
  let cuerpo: unknown = null
  try {
    cuerpo = await respuesta.json()
  } catch {
    // cuerpo vacío o que no es JSON
  }
  if (!respuesta.ok) {
    const { detail, error } = (cuerpo ?? {}) as { detail?: unknown; error?: unknown }
    const mensaje = typeof detail === 'string' && detail ? detail : typeof error === 'string' && error ? error : porDefecto
    throw new ErrorApi(mensaje, respuesta.status)
  }
  return cuerpo as T
}

const JSON_HEADERS = { 'Content-Type': 'application/json' }

export const busquedasRepository = {
  listar: (parametros: URLSearchParams) =>
    pedir<PaginaBusquedas>(
      `${API}/oportunidades?${parametros.toString()}`,
      {},
      'No se pudo cargar el listado de búsquedas.',
    ),

  permisos: () => pedir<PermisosBusquedas>(`${API}/oportunidades/permisos`, {}, 'No se pudieron consultar los permisos.'),

  externosDisponibles: () =>
    pedir<ExternoDisponible[]>(`${API}/externos-disponibles`, {}, 'No se pudieron cargar los usuarios externos.'),

  /** «Cancelar búsqueda» cambia el estado a Cancelada; no elimina nada. */
  cancelar: (id: string) =>
    pedir<Busqueda>(
      `${API}/oportunidades/${id}`,
      { method: 'PUT', headers: JSON_HEADERS, body: JSON.stringify({ estado: 'Cancelada' }) },
      'No se pudo cancelar la búsqueda.',
    ),

  asignarExterno: (id: string, externoId: string) =>
    pedir<Busqueda>(
      `${API}/oportunidades/${id}/externo`,
      { method: 'PUT', headers: JSON_HEADERS, body: JSON.stringify({ externo_id: externoId }) },
      'No se pudo asignar el usuario externo.',
    ),

  quitarExterno: (id: string) =>
    pedir<Busqueda>(`${API}/oportunidades/${id}/externo`, { method: 'DELETE' }, 'No se pudo quitar la asignación.'),
}
