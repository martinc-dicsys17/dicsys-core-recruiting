import { ErrorApi, irAlLoginSiSesionVencida } from '../../candidato-nuevo/api/candidatos.repository'
import type { BusquedaCreada, BusquedaCreate, ItemCatalogo, PermisosBusquedas } from '../types'

/** Acceso a datos del alta de Búsqueda: todo va al backend por el proxy /api/v1 de Flask (agrega el token de la sesión). */
const API = '/api/v1/recruiting'

async function mensajeDeError(respuesta: Response, porDefecto: string): Promise<string> {
  try {
    const cuerpo: unknown = await respuesta.json()
    if (cuerpo && typeof cuerpo === 'object') {
      const { detail, error } = cuerpo as { detail?: unknown; error?: unknown }
      if (typeof detail === 'string' && detail) return detail
      if (typeof error === 'string' && error) return error
    }
  } catch {
    // cuerpo vacío o que no es JSON
  }
  return porDefecto
}

async function pedir<T>(ruta: string, opciones: RequestInit, porDefecto: string): Promise<T> {
  let respuesta: Response
  try {
    respuesta = await fetch(`${API}${ruta}`, {
      ...opciones,
      headers: { Accept: 'application/json', ...opciones.headers },
    })
  } catch {
    throw new ErrorApi('Error de conexión con el servidor.', 0)
  }
  irAlLoginSiSesionVencida(respuesta.status)
  if (!respuesta.ok) throw new ErrorApi(await mensajeDeError(respuesta, porDefecto), respuesta.status)
  return (await respuesta.json()) as T
}

const obtener = <T>(ruta: string, porDefecto: string) => pedir<T>(ruta, {}, porDefecto)

export const nuevaBusquedaRepository = {
  permisos: () => obtener<PermisosBusquedas>('/oportunidades/permisos', 'No se pudieron consultar los permisos.'),
  listarPerfilesPuesto: () =>
    obtener<string[]>('/candidatos/perfiles-puesto', 'No se pudieron cargar los perfiles profesionales.'),
  listarSkills: () => obtener<ItemCatalogo[]>('/skills', 'No se pudieron cargar las tecnologías.'),
  listarHabilidades: () => obtener<ItemCatalogo[]>('/habilidades', 'No se pudieron cargar las competencias.'),
  listarLideres: () => obtener<ItemCatalogo[]>('/lideres', 'No se pudieron cargar los líderes.'),
  listarReclutadores: () => obtener<ItemCatalogo[]>('/reclutadores', 'No se pudieron cargar los reclutadores.'),

  crear: (datos: BusquedaCreate) =>
    pedir<BusquedaCreada>(
      '/oportunidades',
      { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(datos) },
      'Ocurrió un error al guardar la oportunidad.',
    ),
}
