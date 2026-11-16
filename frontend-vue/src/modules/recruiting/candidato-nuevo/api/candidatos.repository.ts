import type { CandidatoCreado, CandidatoCreate, Ciudad, ItemCatalogo, Provincia } from '../types'

/**
 * Acceso a datos de Nuevo Candidato. Todo va al backend real por el proxy /api/v1 de Flask (que agrega el
 * token de la sesión), salvo la subida del CV (multipart), que el proxy no soporta y sigue yendo por la ruta
 * de Flask que ya usaba la pantalla anterior.
 */
const API = '/api/v1/recruiting'

/** Error de la API con el mensaje en castellano que manda el backend ({"detail": "..."}). */
export class ErrorApi extends Error {
  readonly estado: number
  constructor(mensaje: string, estado: number) {
    super(mensaje)
    this.name = 'ErrorApi'
    this.estado = estado
  }
}

async function mensajeDeError(respuesta: Response, porDefecto: string): Promise<string> {
  try {
    const cuerpo: unknown = await respuesta.json()
    if (cuerpo && typeof cuerpo === 'object') {
      const { detail, error } = cuerpo as { detail?: unknown; error?: unknown }
      if (typeof detail === 'string' && detail) return detail
      if (typeof error === 'string' && error) return error
    }
  } catch {
    // cuerpo vacío o que no es JSON: se usa el mensaje por defecto
  }
  return porDefecto
}

async function pedir<T>(ruta: string, opciones: RequestInit, porDefecto: string): Promise<T> {
  let respuesta: Response
  try {
    respuesta = await fetch(ruta, { ...opciones, headers: { Accept: 'application/json', ...opciones.headers } })
  } catch {
    throw new ErrorApi('Error de conexión con el servidor. Reintentá en unos momentos.', 0)
  }
  if (!respuesta.ok) throw new ErrorApi(await mensajeDeError(respuesta, porDefecto), respuesta.status)
  return (await respuesta.json()) as T
}

const obtener = <T>(ruta: string, porDefecto: string) => pedir<T>(`${API}${ruta}`, {}, porDefecto)

export const candidatosRepository = {
  listarProvincias: () => obtener<Provincia[]>('/provincias', 'No se pudieron cargar las provincias.'),
  listarCiudades: (provinciaId: number) =>
    obtener<Ciudad[]>(`/ciudades?provincia_id=${provinciaId}`, 'No se pudieron cargar las ciudades.'),
  listarPerfilesPuesto: () =>
    obtener<string[]>('/candidatos/perfiles-puesto', 'No se pudieron cargar los perfiles profesionales.'),
  listarNivelesSeniority: () =>
    obtener<ItemCatalogo[]>('/niveles-seniority', 'No se pudieron cargar los niveles de seniority.'),
  listarSkills: () => obtener<ItemCatalogo[]>('/skills', 'No se pudieron cargar las tecnologías.'),
  listarHabilidades: () => obtener<ItemCatalogo[]>('/habilidades', 'No se pudieron cargar las competencias.'),

  /**
   * Alta del candidato. Con `busquedaId` (alta desde una búsqueda asignada) usa el endpoint de esa búsqueda,
   * cuya respuesta trae el candidato anidado; sin ella, el alta general en el Banco de Talentos.
   */
  async crear(datos: CandidatoCreate, busquedaId: string): Promise<CandidatoCreado> {
    const ruta = busquedaId ? `/oportunidades/${busquedaId}/candidatos/nuevo` : '/candidatos'
    const respuesta = await pedir<CandidatoCreado | { candidato: CandidatoCreado }>(
      `${API}${ruta}`,
      { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(datos) },
      'Ocurrió un error al guardar el candidato.',
    )
    return 'candidato' in respuesta ? respuesta.candidato : respuesta
  },

  /** Adjunta el CV al candidato recién creado (ruta de Flask, multipart). */
  async subirCv(candidatoId: string, archivo: File): Promise<void> {
    const cuerpo = new FormData()
    cuerpo.append('archivo', archivo)
    await pedir<unknown>(
      `/recruiting/candidatos/${candidatoId}/cv`,
      { method: 'POST', body: cuerpo },
      'No se pudo subir el CV.',
    )
  },
}
