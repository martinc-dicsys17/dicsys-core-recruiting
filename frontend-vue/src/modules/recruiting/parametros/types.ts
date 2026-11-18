/** Tipos de la pantalla Parámetros de Recruiting (configuración, catálogos, archivos de CV e historial). */

export interface ConfigSmartMatching {
  match_minimo_porcentaje: number
}

/** Fila genérica de un ABM: cada catálogo usa las claves que le corresponden. */
export interface RegistroAbm {
  [clave: string]: unknown
  id?: string | number
  nombre?: string
  motivo?: string
  categoria?: string | null
  activo?: boolean
  provincia_id?: number
  ciudad_id?: number
  provincia_nombre?: string | null
  cantidad_ciudades?: number
}

export interface Provincia {
  provincia_id: number
  nombre: string
  cantidad_ciudades: number
}

export interface Ciudad {
  ciudad_id: number
  nombre: string
  provincia_id: number
  provincia_nombre: string | null
}

export interface CampoAbm {
  clave: string
  etiqueta: string
  tipo?: 'texto' | 'select'
  requerido?: boolean
  maxlength?: number
  placeholder?: string
  ayuda?: string
  datalist?: string[]
}

export interface ColumnaAbm {
  clave: string
  etiqueta: string
  tipo?: 'texto' | 'chip' | 'estado' | 'contador'
  alineacion?: 'izquierda' | 'centro' | 'derecha'
  /** Texto cuando el chip viene vacío (por defecto «Sin categoría»; Ciudades usa «-»). */
  vacio?: string
}

export interface ConfigAbm {
  /** Recurso del backend: skills, habilidades, lideres, reclutadores, perfiles-puesto, provincias, ciudades o
   *  motivos-blacklist. */
  ruta: string
  claveId: string
  titulo: string
  subtitulo: string
  nuevo: string
  /** null cuando el catálogo no tiene buscador (provincias y motivos). */
  buscarPlaceholder: string | null
  /** Ancho del buscador (el de Ciudades es más angosto que el resto). */
  buscadorAncho?: string
  camposBusqueda: string[]
  cargando: string
  vacioTitulo: string
  vacioSinFiltro: string
  vacioConFiltro: string
  columnas: ColumnaAbm[]
  campos: CampoAbm[]
  baja: 'logica' | 'fisica'
  tituloEditar: string
  tituloCrear: string
  botonCrear: string
  textoCreado: string
  textoActualizado: string
  /** Texto del confirm() antes de desactivar o eliminar. */
  textoBaja: (registro: RegistroAbm) => string
  textoBajaExitosa: (registro: RegistroAbm) => string
  /** Solo baja lógica: aviso al activar o desactivar desde la columna Estado. */
  textoEstado?: (registro: RegistroAbm, activo: boolean) => string
  errorCargar: string
  errorRequerido: string
  /** Mensaje de red para las operaciones del formulario (las de carga usan `errorCargar`). */
  errorConexion?: string
  /** Mensaje cuando falta un campo de selección obligatorio (por ejemplo, la provincia de una ciudad). */
  errorRequeridoSelect?: string
  /** Estados vacíos simples (una línea centrada) en lugar del bloque con icono y título. */
  vacioSimple?: boolean
}

export interface ArchivoCv {
  nombre: string
  tamano_bytes: number
  tamano: string
  modificado: string
  motivo_error: string | null
  motivo_detalle: string | null
}

export interface CarpetaCvResumen {
  carpeta: string
  cantidad_archivos: number
  tamano_total_bytes: number
  tamano_total: string
}

export interface CarpetaCvDetalle extends CarpetaCvResumen {
  archivos: ArchivoCv[]
  pagina: number | null
  por_pagina: number | null
  total_paginas: number | null
  total_filtrado: number | null
}

export interface BackupEstado {
  backup_id: string
  estado: 'preparando' | 'generando' | 'verificando' | 'finalizado' | 'error'
  fase: string | null
  porcentaje: number
  mensaje: string | null
  nombre_archivo: string | null
  tamano: string | null
  sha256: string | null
  error: string | null
}

export interface BackupSeguridad {
  backup_id: string
  nombre_archivo: string
  tamano: string
}

export interface ImportacionEstado {
  importacion_id: string
  estado: 'validando' | 'validado' | 'rechazado' | 'restaurando' | 'finalizado' | 'error'
  fase: string | null
  porcentaje: number
  mensaje: string | null
  error: string | null
  nombre_original: string | null
  tamano: string | null
  preview: {
    integridad: { detalle: string }
    generado_utc: string
    version_backup: string
    generado_por: string | null
    tamano_total: string
    tamano_zip: string
    total_registros: number
    total_tablas: number
    carpetas: { carpeta: string; cantidad: number; tamano: string }[]
    tablas: { tabla: string; registros: number }[]
  } | null
  limitaciones: string[]
  avisos: string[]
  backup_seguridad: BackupSeguridad | null
  resultado: {
    total_registros: number
    total_archivos: number
    archivos_storage: number | null
    backup_seguridad: BackupSeguridad | null
    usuarios_sin_credenciales: { id: string; email: string }[]
  } | null
  revertido: boolean | null
}

export interface LimpiezaResumen {
  registros: Record<string, number>
  archivos: Record<string, number>
  total_registros: number
  total_archivos: number
}

export interface HistorialCargaCvItem {
  id: string
  fecha_operacion: string
  usuario_nombre: string
  tipo_carga: string
  total_archivos: number
  candidatos_creados: number
  duplicados: number
  sin_email: number
  rechazados: number
  resultado: string
}

export interface HistorialCargaCvPagina {
  items: HistorialCargaCvItem[]
  total: number
  pagina: number
  por_pagina: number
  total_paginas: number
}

export interface HistorialCargaCvArchivo {
  orden: number
  nombre_archivo: string
  resultado: string
  motivo: string | null
}

export interface HistorialCargaCvDetalle {
  operacion: HistorialCargaCvItem
  archivos: HistorialCargaCvArchivo[]
}
