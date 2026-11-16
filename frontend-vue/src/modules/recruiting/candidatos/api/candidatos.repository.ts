import { ErrorApi } from '../../candidato-nuevo/api/candidatos.repository'
import type {
  AvanceLote,
  BusquedaElegible,
  ComparacionCv,
  PaginaCandidatos,
  PermisosCandidatos,
  ResultadoCargaCv,
} from '../types'

/**
 * Acceso a datos de la grilla de Candidatos. Listado, permisos, catálogos y baja van al backend real por el
 * proxy /api/v1 de Flask (que agrega el token de la sesión). Las cargas de CV (multipart) y las acciones de
 * «Asignar a búsqueda» y «Ver detalles» siguen yendo por las rutas de Flask que ya usaba la pantalla anterior.
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
    return await fetch(ruta, { ...opciones, headers: { Accept: 'application/json', ...opciones.headers } })
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

const obtener = <T>(ruta: string, porDefecto: string) => pedir<T>(ruta, {}, porDefecto)

interface SkillCatalogo {
  nombre: string
  categoria?: string | null
}

export const candidatosRepository = {
  listar: (parametros: URLSearchParams) =>
    obtener<PaginaCandidatos>(
      `${API}/candidatos?${parametros.toString()}`,
      'No se pudo cargar el listado de candidatos.',
    ),

  permisos: () =>
    obtener<PermisosCandidatos>(`${API}/candidatos/permisos`, 'No se pudieron consultar los permisos.'),

  listarSkillsConCategoria: () => obtener<SkillCatalogo[]>(`${API}/skills`, 'No se pudieron cargar las categorías.'),

  async eliminar(id: string): Promise<void> {
    await pedir<unknown>(`${API}/candidatos/${id}`, { method: 'DELETE' }, 'Error al eliminar el candidato.')
  },

  /** Primera postulación del candidato (la que abre «Ver detalles»), o null si no tiene. */
  async primeraPostulacion(id: string): Promise<string | null> {
    const lista = await obtener<{ oportunidad_id?: string }[]>(
      `${FLASK}/candidatos/${id}/pipelines`,
      'No se pudieron consultar las postulaciones.',
    )
    return (Array.isArray(lista) && lista[0]?.oportunidad_id) || null
  },

  busquedasElegibles: async (id: string) => {
    const lista = await obtener<BusquedaElegible[]>(
      `${FLASK}/candidatos/${id}/busquedas-elegibles`,
      'No se pudieron cargar las búsquedas elegibles.',
    )
    return Array.isArray(lista) ? lista : []
  },

  async asignarABusqueda(busquedaId: string, candidatoId: string): Promise<void> {
    const respuesta = await enviar(`${FLASK}/oportunidades/${busquedaId}/candidatos`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ candidato_id: candidatoId }),
    })
    const cuerpo = await leerJson(respuesta)
    const fallo = !respuesta.ok || (cuerpo as { success?: boolean } | null)?.success === false
    if (fallo) throw new ErrorApi(mensajeDe(cuerpo, 'Ocurrió un error al asignar el candidato a la búsqueda.'), respuesta.status)
  },

  /**
   * Carga individual: crea el candidato desde el CV. Con el email de uno existente y un CV distinto el backend
   * responde 409 con ambos CV para compararlos; `confirmar` (actualizar-cv) reemplaza el CV de esa ficha.
   */
  async cargarCv(archivo: File, confirmar: boolean): Promise<ResultadoCargaCv> {
    const cuerpo = new FormData()
    cuerpo.append('archivo', archivo)
    const respuesta = await enviar(`${FLASK}/candidatos/${confirmar ? 'actualizar-cv' : 'cargar-cv'}`, {
      method: 'POST',
      body: cuerpo,
    })
    const datos = (await leerJson(respuesta)) as
      | { ok?: boolean; success?: boolean; requiere_comparacion?: boolean; actual?: ComparacionCv['actual']; nuevo?: ComparacionCv['nuevo'] }
      | null
    if (respuesta.ok && datos && (datos.ok === true || datos.success === true)) return { tipo: 'ok' }
    if (respuesta.status === 409 && datos?.requiere_comparacion) {
      return { tipo: 'comparar', comparacion: { actual: datos.actual ?? {}, nuevo: datos.nuevo ?? {} } }
    }
    throw new ErrorApi(mensajeDe(datos, 'Error al procesar el archivo'), respuesta.status)
  },

  async iniciarLote(archivos: File[]): Promise<string> {
    const cuerpo = new FormData()
    archivos.forEach((a) => cuerpo.append('archivos', a))
    const respuesta = await enviar(`${FLASK}/candidatos/cargar-cv-masivo/iniciar`, { method: 'POST', body: cuerpo })
    const datos = (await leerJson(respuesta)) as { lote_id?: string } | null
    if (!respuesta.ok || !datos?.lote_id) {
      throw new ErrorApi(mensajeDe(datos, 'Ocurrió un error al procesar el lote de CVs.'), respuesta.status)
    }
    return datos.lote_id
  },

  /** Avance del lote; se corta a los 20 s para no dejar la pantalla cargando para siempre. */
  async avanceLote(lote: string): Promise<AvanceLote> {
    const respuesta = await enviar(`${FLASK}/candidatos/cargar-cv-masivo/${encodeURIComponent(lote)}/estado`, {
      signal: AbortSignal.timeout(20_000),
    })
    const datos = await leerJson(respuesta)
    if (!respuesta.ok) throw new ErrorApi(mensajeDe(datos, 'No se pudo consultar el avance.'), respuesta.status)
    return datos as AvanceLote
  },

  async cancelarLote(lote: string): Promise<void> {
    const respuesta = await enviar(`${FLASK}/candidatos/cargar-cv-masivo/${encodeURIComponent(lote)}/cancelar`, {
      method: 'POST',
    })
    if (!respuesta.ok) throw new ErrorApi('No se pudo cancelar la carga. Intentá nuevamente.', respuesta.status)
  },
}

/** Descarga o vista previa de un CV guardado (ruta de Flask). */
export const urlCv = (clave: string): string => `/storage/${clave}`

/** Vista previa en PDF de un CV Word: la conversión la hace el backend (rutas de Flask). */
export async function previsualizarWord(origen: { clave: string } | { archivo: File }): Promise<string | null> {
  try {
    const respuesta =
      'clave' in origen
        ? await fetch(`/storage/preview-pdf/${origen.clave}`)
        : await fetch('/storage/preview-pdf', { method: 'POST', body: (() => { const f = new FormData(); f.append('archivo', origen.archivo); return f })() })
    if (!respuesta.ok || !/pdf/i.test(respuesta.headers.get('content-type') ?? '')) return null
    return URL.createObjectURL(await respuesta.blob())
  } catch {
    return null
  }
}
