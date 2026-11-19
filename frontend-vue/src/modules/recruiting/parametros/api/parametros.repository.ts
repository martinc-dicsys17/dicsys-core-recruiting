import { ErrorApi, irAlLoginSiSesionVencida } from '../../candidato-nuevo/api/candidatos.repository'
import type {
  BackupEstado,
  CarpetaCvDetalle,
  CarpetaCvResumen,
  ConfigSmartMatching,
  HistorialCargaCvDetalle,
  HistorialCargaCvPagina,
  ImportacionEstado,
  LimpiezaResumen,
  RegistroAbm,
} from '../types'

/**
 * Acceso a datos de Parámetros. Las operaciones JSON van al backend real por el proxy /api/v1 de Flask (que agrega el
 * token de la sesión). La subida del backup (multipart), las descargas (streaming) y la limpieza de datos (más larga que
 * el timeout del proxy JSON) siguen por las rutas de Flask que ya usaba la pantalla anterior.
 */
const API = '/api/v1/recruiting/parametros'
const FLASK = '/recruiting/parametros'

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
  let respuesta: Response
  try {
    respuesta = await fetch(ruta, { ...opciones, headers: { Accept: 'application/json', ...opciones.headers } })
  } catch {
    throw new ErrorApi('Error de conexión con el servidor. Reintentá en unos momentos.', 0)
  }
  irAlLoginSiSesionVencida(respuesta.status)
  return respuesta
}

async function pedir<T>(ruta: string, opciones: RequestInit, porDefecto: string): Promise<T> {
  const respuesta = await enviar(ruta, opciones)
  const cuerpo = await leerJson(respuesta)
  if (!respuesta.ok) throw new ErrorApi(mensajeDe(cuerpo, porDefecto), respuesta.status)
  return cuerpo as T
}

const obtener = <T>(ruta: string, porDefecto: string, senal?: AbortSignal) =>
  pedir<T>(ruta, senal ? { signal: senal } : {}, porDefecto)

/**
 * Rutas propias de Flask (las de la pantalla anterior): responden `{success: true, <clave>}` o
 * `{success: false, error}`. Se usan cuando la operación no entra en el proxy JSON genérico (por ejemplo, la limpieza
 * de datos, que puede tardar más que su timeout).
 */
async function pedirFlask<T>(ruta: string, opciones: RequestInit, clave: string, porDefecto: string): Promise<T> {
  const respuesta = await enviar(ruta, opciones)
  const cuerpo = (await leerJson(respuesta)) as Record<string, unknown> | null
  if (!respuesta.ok || !cuerpo || cuerpo.success !== true || !(clave in cuerpo)) {
    throw new ErrorApi(mensajeDe(cuerpo, porDefecto), respuesta.status)
  }
  return cuerpo[clave] as T
}

/**
 * Mensajes cuando el backend no manda un `detail` legible: los mismos que armaba el proxy de Flask de la pantalla
 * anterior (`Error al cargar <lista>.`, `Error al crear <singular>.`...).
 */
interface TextosRecurso {
  lista: string
  singular: string
}

/** Recurso de un catálogo con baja lógica: listar con inactivos, crear, editar y desactivar. */
function recursoAbm(ruta: string, textos: TextosRecurso) {
  return {
    listar: (parametros = '') =>
      obtener<RegistroAbm[]>(
        `${API}/${ruta}?activo_only=false${parametros ? `&${parametros}` : ''}`,
        `Error al cargar ${textos.lista}.`,
      ),
    crear: (datos: Record<string, unknown>) =>
      pedir<RegistroAbm>(
        `${API}/${ruta}`,
        { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(datos) },
        `Error al crear ${textos.singular}.`,
      ),
    actualizar: (id: string | number, datos: Record<string, unknown>) =>
      pedir<RegistroAbm>(
        `${API}/${ruta}/${encodeURIComponent(String(id))}`,
        { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(datos) },
        `Error al actualizar ${textos.singular}.`,
      ),
    desactivar: (id: string | number) =>
      pedir<RegistroAbm>(
        `${API}/${ruta}/${encodeURIComponent(String(id))}`,
        { method: 'DELETE' },
        `Error al desactivar ${textos.singular}.`,
      ),
  }
}

/** Recurso de un catálogo sin baja lógica: el DELETE elimina el registro. */
function recursoUbicacion(ruta: string, textos: TextosRecurso) {
  return {
    listar: (parametros = '') =>
      obtener<RegistroAbm[]>(`${API}/${ruta}${parametros ? `?${parametros}` : ''}`, `Error al cargar ${textos.lista}.`),
    crear: (datos: Record<string, unknown>) =>
      pedir<RegistroAbm>(
        `${API}/${ruta}`,
        { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(datos) },
        `Error al crear ${textos.singular}.`,
      ),
    actualizar: (id: string | number, datos: Record<string, unknown>) =>
      pedir<RegistroAbm>(
        `${API}/${ruta}/${encodeURIComponent(String(id))}`,
        { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(datos) },
        `Error al actualizar ${textos.singular}.`,
      ),
    eliminar: (id: string | number) =>
      pedir<unknown>(
        `${API}/${ruta}/${encodeURIComponent(String(id))}`,
        { method: 'DELETE' },
        `Error al eliminar ${textos.singular}.`,
      ),
  }
}

export const parametrosRepository = {
  config: {
    obtener: () => obtener<ConfigSmartMatching>(`${API}/config`, 'No se pudo cargar la configuración.'),
    guardar: (matchMinimo: number) =>
      pedir<ConfigSmartMatching>(
        `${API}/config`,
        { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ match_minimo_porcentaje: matchMinimo }) },
        'Error al guardar',
      ),
  },

  skills: recursoAbm('skills', { lista: 'skills', singular: 'la skill' }),
  habilidades: recursoAbm('habilidades', { lista: 'habilidades', singular: 'la habilidad' }),
  lideres: recursoAbm('lideres', { lista: 'lideres', singular: 'el líder' }),
  reclutadores: recursoAbm('reclutadores', { lista: 'reclutadores', singular: 'el reclutador' }),
  perfiles: recursoAbm('perfiles-puesto', { lista: 'perfiles', singular: 'el perfil profesional' }),

  provincias: recursoUbicacion('provincias', { lista: 'provincias', singular: 'la provincia' }),
  ciudades: recursoUbicacion('ciudades', { lista: 'ciudades', singular: 'la ciudad' }),
  motivos: recursoUbicacion('motivos-blacklist', { lista: 'motivos', singular: 'el motivo' }),

  archivos: {
    resumen: () => obtener<CarpetaCvResumen[]>(`${API}/archivos-cv`, 'No se pudieron consultar las carpetas de CV.'),
    detalle: (carpeta: string, parametros: string) =>
      obtener<CarpetaCvDetalle>(
        `${API}/archivos-cv/${encodeURIComponent(carpeta)}?${parametros}`,
        'No se pudo consultar el contenido de la carpeta.',
      ),
    /**
     * Limpieza de datos de Recruiting: por la ruta de Flask de la pantalla anterior, que espera al backend hasta 120 s
     * (el proxy /api/v1 corta a los 10 s y la limpieza es sincrónica: un corte informaría un error falso cuando los
     * registros ya se borraron). Flask manda `{"confirmar": true}` y valida el administrador; el backend lo revalida.
     */
    limpiar: () =>
      pedirFlask<LimpiezaResumen>(
        `${FLASK}/archivos-cv/limpiar-bd`,
        { method: 'POST', headers: { 'Content-Type': 'application/json' } },
        'resumen',
        'No se pudo completar la limpieza.',
      ),
    iniciarBackup: () =>
      pedir<BackupEstado>(`${API}/archivos-cv/backup/iniciar`, { method: 'POST' }, 'No se pudo iniciar el backup.'),
    estadoBackup: (backupId: string, senal?: AbortSignal) =>
      obtener<BackupEstado>(
        `${API}/archivos-cv/backup/${encodeURIComponent(backupId)}/estado`,
        'No se pudo consultar el backup.',
        senal,
      ),
    descargarBackup: (backupId: string) =>
      `${FLASK}/archivos-cv/backup/${encodeURIComponent(backupId)}/descargar`,
    subirImportacion: (archivo: File, progreso: (porcentaje: number) => void, senal?: AbortSignal) =>
      new Promise<ImportacionEstado>((resolver, rechazar) => {
        const datos = new FormData()
        datos.append('archivo', archivo)
        const xhr = new XMLHttpRequest()
        senal?.addEventListener('abort', () => xhr.abort(), { once: true })
        xhr.onabort = () => rechazar(new ErrorApi('Se canceló la subida del backup.', 0))
        xhr.open('POST', `${FLASK}/archivos-cv/importar/subir`)
        xhr.setRequestHeader('Accept', 'application/json')
        xhr.upload.onprogress = (evento) => {
          if (evento.lengthComputable) progreso(Math.round((100 * evento.loaded) / evento.total))
        }
        xhr.onload = () => {
          let cuerpo: unknown = null
          try {
            cuerpo = JSON.parse(xhr.responseText)
          } catch {
            cuerpo = null
          }
          if (xhr.status >= 200 && xhr.status < 300) {
            const datosCuerpo = cuerpo as { success?: boolean; importacion?: ImportacionEstado } | null
            if (datosCuerpo?.success && datosCuerpo.importacion) {
              resolver(datosCuerpo.importacion)
              return
            }
            rechazar(new ErrorApi(mensajeDe(cuerpo, 'No se pudo subir el backup.'), xhr.status))
            return
          }
          rechazar(new ErrorApi(mensajeDe(cuerpo, 'No se pudo subir el backup.'), xhr.status))
        }
        xhr.onerror = () => rechazar(new ErrorApi('Error de conexión al subir el backup.', 0))
        xhr.send(datos)
      }),
    estadoImportacion: (importacionId: string, senal?: AbortSignal) =>
      obtener<ImportacionEstado>(
        `${API}/archivos-cv/importar/${encodeURIComponent(importacionId)}/estado`,
        'No se pudo consultar la importación.',
        senal,
      ),
    confirmarImportacion: (importacionId: string, textoConfirmacion: string, aceptarLimitaciones: boolean) =>
      pedir<ImportacionEstado>(
        `${API}/archivos-cv/importar/${encodeURIComponent(importacionId)}/confirmar`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ confirmar: true, texto_confirmacion: textoConfirmacion, aceptar_limitaciones: aceptarLimitaciones }),
        },
        'No se pudo iniciar la restauración.',
      ),
    descartarImportacion: (importacionId: string) =>
      pedir<unknown>(
        `${API}/archivos-cv/importar/${encodeURIComponent(importacionId)}`,
        { method: 'DELETE' },
        'No se pudo descartar el backup.',
      ),
    urlDescargar: (carpeta: string, nombre: string) =>
      `${FLASK}/archivos-cv/${encodeURIComponent(carpeta)}/descargar?nombre=${encodeURIComponent(nombre)}`,
    urlDescargarTodos: (carpeta: string) => `${FLASK}/archivos-cv/${encodeURIComponent(carpeta)}/descargar-todos`,
  },

  historial: {
    listar: (parametros: string) =>
      obtener<HistorialCargaCvPagina>(
        `${API}/historial-cargas-cv?${parametros}`,
        'No se pudo consultar el historial.',
      ),
    detalle: (id: string) =>
      obtener<HistorialCargaCvDetalle>(
        `${API}/historial-cargas-cv/${encodeURIComponent(id)}`,
        'No se pudo consultar el detalle.',
      ),
  },
}
