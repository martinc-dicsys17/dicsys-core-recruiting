import { ErrorApi, irAlLoginSiSesionVencida } from '../../candidato-nuevo/api/candidatos.repository'
import type {
  CandidatoAsignado,
  CandidatoSugerido,
  ExternoDisponible,
  Oportunidad,
  PermisosBusquedas,
} from '../types'

/**
 * Acceso a datos de la ficha de una Búsqueda. Todo va al backend real por el proxy /api/v1 de Flask (que agrega el
 * token de la sesión), salvo la carga de un CV (multipart), que el proxy no soporta y sigue yendo por la ruta de
 * Flask que ya usaba la pantalla anterior (`/recruiting/oportunidades/<id>/cargar-cv`).
 */
const API = '/api/v1/recruiting'
const FLASK = '/recruiting'

export { ErrorApi }

async function leerJson(respuesta: Response): Promise<unknown> {
  try {
    return await respuesta.json()
  } catch {
    return null
  }
}

function mensajeDe(cuerpo: unknown, porDefecto: string): string {
  if (cuerpo && typeof cuerpo === 'object') {
    const { detail, error } = cuerpo as { detail?: unknown; error?: unknown }
    if (typeof detail === 'string' && detail) return detail
    if (typeof error === 'string' && error) return error
  }
  return porDefecto
}

async function enviar(ruta: string, opciones: RequestInit): Promise<Response> {
  try {
    const respuesta = await fetch(ruta, { ...opciones, headers: { Accept: 'application/json', ...opciones.headers } })
    irAlLoginSiSesionVencida(respuesta.status)
    return respuesta
  } catch {
    throw new ErrorApi('Error de conexión con el servidor. Reintentá en unos momentos.', 0)
  }
}

/** Pide y devuelve el JSON; un error HTTP se convierte en ErrorApi con el mensaje del backend. */
async function pedir<T>(ruta: string, opciones: RequestInit, porDefecto: string): Promise<T> {
  const respuesta = await enviar(ruta, opciones)
  const cuerpo = await leerJson(respuesta)
  if (!respuesta.ok) throw new ErrorApi(mensajeDe(cuerpo, porDefecto), respuesta.status)
  return cuerpo as T
}

const obtener = <T>(ruta: string, porDefecto: string) => pedir<T>(`${API}${ruta}`, {}, porDefecto)
const enviarJson = <T>(metodo: string, ruta: string, cuerpo: unknown, porDefecto: string) =>
  pedir<T>(
    `${API}${ruta}`,
    { method: metodo, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(cuerpo) },
    porDefecto,
  )

interface ItemCatalogo {
  nombre?: string
}
const ordenar = (nombres: string[]) => nombres.slice().sort((a, b) => a.localeCompare(b, undefined, { sensitivity: 'base' }))
const nombresDe = (lista: ItemCatalogo[]): string[] =>
  (Array.isArray(lista) ? lista : []).map((i) => i?.nombre ?? '').filter(Boolean)

export interface ResultadoCargaCv {
  mensaje: string
  /** 202: el CV es distinto al de un candidato existente y el caso se derivó a Recruiting. */
  derivado: boolean
}

export const busquedaRepository = {
  /** La búsqueda; el mensaje distingue «sin acceso» (403) de «no existe» como la pantalla anterior. */
  async obtener(id: string): Promise<Oportunidad> {
    const respuesta = await enviar(`${API}/oportunidades/${id}`, {})
    const cuerpo = await leerJson(respuesta)
    if (!respuesta.ok || !cuerpo || typeof cuerpo !== 'object') {
      throw new ErrorApi(
        respuesta.status === 403
          ? 'No tenés acceso a esta búsqueda: no la tenés asignada.'
          : 'La búsqueda solicitada no existe o no fue encontrada.',
        respuesta.status,
      )
    }
    return cuerpo as Oportunidad
  },

  permisos: () =>
    obtener<PermisosBusquedas>('/oportunidades/permisos', 'No se pudieron consultar los permisos.'),

  candidatos: (id: string) =>
    obtener<CandidatoAsignado[]>(`/oportunidades/${id}/candidatos`, 'No se pudieron cargar los candidatos.'),

  compatibles: (id: string) =>
    obtener<CandidatoSugerido[]>(
      `/oportunidades/${id}/candidatos-compatibles`,
      'No se pudieron cargar las sugerencias.',
    ),

  async matchMinimo(): Promise<number> {
    const config = await obtener<{ match_minimo_porcentaje?: number }>('/config', 'No se pudo cargar la configuración.')
    return config.match_minimo_porcentaje ?? 50
  },

  async reclutadores(): Promise<string[]> {
    return nombresDe(await obtener<ItemCatalogo[]>('/reclutadores', 'No se pudieron cargar los reclutadores.'))
  },

  externosDisponibles: async (): Promise<ExternoDisponible[]> =>
    (await obtener<ExternoDisponible[]>('/externos-disponibles', 'No se pudieron cargar los usuarios externos.')).filter(
      (u) => u && u.id,
    ),

  async skills(): Promise<string[]> {
    return ordenar(nombresDe(await obtener<ItemCatalogo[]>('/skills', 'No se pudieron cargar las tecnologías.')))
  },

  async habilidades(): Promise<string[]> {
    return ordenar(nombresDe(await obtener<ItemCatalogo[]>('/habilidades', 'No se pudieron cargar las competencias.')))
  },

  async perfilesPuesto(): Promise<string[]> {
    const lista = await obtener<string[]>('/candidatos/perfiles-puesto', 'No se pudieron cargar los perfiles profesionales.')
    return lista.filter((p) => typeof p === 'string' && p.trim())
  },

  /** Edición parcial: solo viaja lo que se manda (la ficha edita Descripción y Skills deseadas). */
  actualizar: (id: string, cambios: { skills_deseadas: string[]; descripcion: string | null }) =>
    enviarJson<Oportunidad>('PUT', `/oportunidades/${id}`, cambios, 'Ocurrió un error al actualizar la búsqueda.'),

  asignarReclutador: (id: string, nombre: string) =>
    enviarJson<Oportunidad>(
      'POST',
      `/oportunidades/${id}/reclutador`,
      { recruiter_nombre: nombre.trim() },
      'No se pudo asignar el reclutador.',
    ),

  asignarExterno: (id: string, externoId: string) =>
    enviarJson<Oportunidad>(
      'PUT',
      `/oportunidades/${id}/externo`,
      { externo_id: externoId },
      'No se pudo asignar el usuario externo.',
    ),

  quitarExterno: (id: string) =>
    pedir<Oportunidad>(`${API}/oportunidades/${id}/externo`, { method: 'DELETE' }, 'No se pudo quitar la asignación.'),

  /** «Postular a Búsqueda»: suma el candidato sugerido al pipeline de la búsqueda. */
  async postular(id: string, candidatoId: string): Promise<void> {
    await enviarJson<unknown>(
      'POST',
      `/oportunidades/${id}/candidatos`,
      { candidato_id: candidatoId, etapa: 'Postulado', estado: 'En proceso', observaciones: null },
      'Error en la postulación',
    )
  },

  /** Carga un CV desde una búsqueda asignada (grupo EXTERNOS): crea el candidato y lo asocia a la búsqueda. */
  async cargarCv(id: string, archivo: File): Promise<ResultadoCargaCv> {
    const formulario = new FormData()
    formulario.append('archivo', archivo)
    const respuesta = await enviar(`${FLASK}/oportunidades/${id}/cargar-cv`, { method: 'POST', body: formulario })
    const cuerpo = (await leerJson(respuesta)) as { ok?: boolean; mensaje?: string; error?: string } | null
    if (respuesta.ok && cuerpo?.ok) {
      return {
        derivado: respuesta.status === 202,
        mensaje: cuerpo.mensaje || 'CV cargado y candidato asociado a la búsqueda.',
      }
    }
    throw new ErrorApi(cuerpo?.error || 'No se pudo cargar el CV.', respuesta.status)
  },
}
