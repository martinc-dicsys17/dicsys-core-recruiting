/**
 * Aviso para la pantalla siguiente. La pantalla anterior usaba el mensaje «flash» de Flask (redirigía al listado y el
 * aviso se veía allí); al ser el listado una pantalla Vue, el aviso viaja por sessionStorage y el listado lo muestra
 * una sola vez al abrirse.
 */
const CLAVE = 'busquedasAviso'

export interface AvisoPendiente {
  tipo: 'error' | 'success'
  mensaje: string
}

export function guardarAviso(aviso: AvisoPendiente): void {
  try {
    sessionStorage.setItem(CLAVE, JSON.stringify(aviso))
  } catch {
    // sin sessionStorage el aviso se omite, pero la navegación continúa
  }
}

/** Devuelve el aviso pendiente (si hay) y lo borra. */
export function tomarAviso(): AvisoPendiente | null {
  try {
    const crudo = sessionStorage.getItem(CLAVE)
    if (!crudo) return null
    sessionStorage.removeItem(CLAVE)
    const aviso = JSON.parse(crudo) as Partial<AvisoPendiente>
    return typeof aviso.mensaje === 'string' ? { tipo: aviso.tipo === 'success' ? 'success' : 'error', mensaje: aviso.mensaje } : null
  } catch {
    return null
  }
}
