import { ErrorApi, irAlLoginSiSesionVencida } from '../../candidato-nuevo/api/candidatos.repository'
import { formularioCambio } from '../movimientos'
import { ERROR_PIPELINE } from '../presentacion'
import type {
  AlcanceCandidatos,
  BusquedaAbierta,
  BusquedaPipeline,
  CambioEtapa,
  CandidatoColumna,
  CandidatoPipeline,
  MotivoDescarte,
  PaginaBusquedas,
  PermisosPipeline,
  ResumenGlobal,
} from '../types'

/**
 * Acceso a datos de Pipeline. Las consultas van al backend real por el proxy /api/v1 de Flask (que agrega el token de
 * la sesión). Mover de etapa, descartar y reingresar siguen yendo por la ruta de Flask que ya usaba la pantalla
 * anterior (`/recruiting/oportunidades/<id>/candidatos/<id>/etapa`): admite el archivo adjunto (multipart, que el proxy
 * no soporta) y lo guarda después del cambio de etapa, con las mismas validaciones.
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
    const { error, detail } = cuerpo as { detail?: unknown; error?: unknown }
    if (typeof error === 'string' && error) return error
    if (typeof detail === 'string' && detail) return detail
  }
  return porDefecto
}

async function enviar(ruta: string, opciones: RequestInit = {}): Promise<Response> {
  let respuesta: Response
  try {
    respuesta = await fetch(ruta, { ...opciones, headers: { Accept: 'application/json', ...opciones.headers } })
  } catch {
    throw new ErrorApi('Error de conexión con el servidor. Reintentá en unos momentos.', 0)
  }
  irAlLoginSiSesionVencida(respuesta.status)
  return respuesta
}

async function obtener<T>(ruta: string, porDefecto: string): Promise<T> {
  const respuesta = await enviar(`${API}${ruta}`)
  const cuerpo = await leerJson(respuesta)
  if (!respuesta.ok) throw new ErrorApi(mensajeDe(cuerpo, porDefecto), respuesta.status)
  return cuerpo as T
}

const conAlcance = (alcance: AlcanceCandidatos, separador: '?' | '&' = '?') =>
  alcance ? `${separador}alcance_candidatos=${encodeURIComponent(alcance)}` : ''

/**
 * Resultado de mover, descartar o reingresar. `ok: false` lleva el mensaje del backend (o el de Flask). Un error de red
 * o una respuesta que no es JSON se informa como `ErrorApi` de estado 0, igual que la pantalla anterior («Error de red»).
 */
export type ResultadoCambio = { ok: true } | { ok: false; mensaje: string }

export const pipelineRepository = {
  permisos: () => obtener<PermisosPipeline>('/pipeline-permisos', 'No se pudieron consultar los permisos.'),

  /** Vista global: solo las búsquedas Abiertas, como la pantalla anterior. */
  resumen: (alcance: AlcanceCandidatos) =>
    obtener<ResumenGlobal>(
      `/pipeline-resumen?estado=Abierta&alcance_candidatos=${encodeURIComponent(alcance)}`,
      ERROR_PIPELINE,
    ),

  /** Selección del Pipeline individual: las búsquedas Abiertas (hasta 100). */
  async busquedasAbiertas(): Promise<BusquedaAbierta[]> {
    const pagina = await obtener<PaginaBusquedas>('/oportunidades?estado=Abierta&por_pagina=100', ERROR_PIPELINE)
    return (pagina?.items ?? []).filter((op) => String(op.estado ?? '').trim().toLowerCase() === 'abierta')
  },

  /** Candidatos de una búsqueda en una columna de la vista global (detalle emergente). */
  candidatosDeColumna: (busquedaId: string, columna: string, alcance: AlcanceCandidatos) =>
    obtener<CandidatoColumna[]>(
      `/oportunidades/${encodeURIComponent(busquedaId)}/pipeline-columna/${encodeURIComponent(columna)}${conAlcance(alcance)}`,
      'No se pudo obtener el detalle de candidatos',
    ),

  /** La búsqueda; el estado del error distingue «sin acceso» (403) de «no existe». */
  async busqueda(id: string): Promise<BusquedaPipeline> {
    const respuesta = await enviar(`${API}/oportunidades/${id}`)
    const cuerpo = await leerJson(respuesta)
    if (!respuesta.ok || !cuerpo || typeof cuerpo !== 'object') {
      throw new ErrorApi(
        respuesta.status === 403
          ? 'No tenés acceso a esta búsqueda: no la tenés asignada.'
          : 'La búsqueda solicitada no existe o no fue encontrada.',
        respuesta.status,
      )
    }
    return cuerpo as BusquedaPipeline
  },

  candidatos: (id: string, alcance: AlcanceCandidatos) =>
    obtener<CandidatoPipeline[]>(`/oportunidades/${id}/pipeline-candidatos${conAlcance(alcance)}`, ERROR_PIPELINE),

  /** Motivos de descarte de la etapa; sin motivos es un error, como en la pantalla anterior. */
  async motivosDescarte(etapa: string): Promise<MotivoDescarte[]> {
    const motivos = await obtener<MotivoDescarte[]>(
      `/motivos-descarte?etapa=${encodeURIComponent(etapa)}`,
      'Respuesta sin motivos',
    )
    if (!Array.isArray(motivos) || motivos.length === 0) throw new ErrorApi('Respuesta sin motivos', 200)
    return motivos
  },

  /** Mueve de etapa, descarta o reingresa; con archivo, lo adjunta a la etapa (multipart). */
  async cambiarEtapa(
    busquedaId: string,
    candidatoId: string,
    cambio: CambioEtapa,
    archivo: File | null,
    porDefecto: string,
  ): Promise<ResultadoCambio> {
    const ruta = `${FLASK}/oportunidades/${busquedaId}/candidatos/${candidatoId}/etapa`
    const respuesta = archivo
      ? await enviar(ruta, { method: 'POST', body: formularioCambio(cambio, archivo) })
      : await enviar(ruta, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(cambio) })
    let cuerpo: unknown
    try {
      cuerpo = await respuesta.json()
    } catch {
      throw new ErrorApi('Respuesta inválida del servidor.', 0)
    }
    const exito = respuesta.ok && (cuerpo as { success?: unknown } | null)?.success !== false
    return exito ? { ok: true } : { ok: false, mensaje: mensajeDe(cuerpo, porDefecto) }
  },
}
