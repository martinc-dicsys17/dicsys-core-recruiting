import { URL_BACKEND } from './stack'

/** Cliente mínimo del backend del stack E2E (solo para sembrar y para comprobar resultados). Datos ficticios. */
export const ADMIN = { email: 'admin@admin.com', password: 'E2e-Admin-2026!' }

export class ClienteApi {
  constructor(private token = '') {}

  static async ingresar(email: string, password: string): Promise<ClienteApi> {
    const r = await fetch(`${URL_BACKEND}/api/v1/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    })
    const cuerpo = (await r.json()) as { access_token?: string }
    if (!r.ok || !cuerpo.access_token) throw new Error(`Login de ${email} falló: ${r.status}`)
    return new ClienteApi(cuerpo.access_token)
  }

  async pedir<T = unknown>(metodo: string, ruta: string, cuerpo?: unknown, esperado = [200, 201, 202]): Promise<{ estado: number; datos: T }> {
    const r = await fetch(`${URL_BACKEND}/api/v1${ruta}`, {
      method: metodo,
      headers: { Authorization: `Bearer ${this.token}`, ...(cuerpo !== undefined ? { 'Content-Type': 'application/json' } : {}) },
      body: cuerpo !== undefined ? JSON.stringify(cuerpo) : undefined,
    })
    const texto = await r.text()
    let datos: unknown = null
    try {
      datos = texto ? JSON.parse(texto) : null
    } catch {
      datos = texto
    }
    if (!esperado.includes(r.status)) throw new Error(`${metodo} ${ruta} -> ${r.status}: ${texto.slice(0, 300)}`)
    return { estado: r.status, datos: datos as T }
  }

  get = <T = unknown>(ruta: string) => this.pedir<T>('GET', ruta).then((r) => r.datos)
  post = <T = unknown>(ruta: string, cuerpo: unknown, esperado?: number[]) => this.pedir<T>('POST', ruta, cuerpo, esperado).then((r) => r.datos)
  put = <T = unknown>(ruta: string, cuerpo: unknown) => this.pedir<T>('PUT', ruta, cuerpo).then((r) => r.datos)

  /** Subida multipart de un archivo (campo `archivo`). */
  async subirArchivo<T = unknown>(ruta: string, nombre: string, contenido: Buffer, tipo = 'application/pdf'): Promise<T> {
    const f = new FormData()
    f.append('archivo', new Blob([new Uint8Array(contenido)], { type: tipo }), nombre)
    const r = await fetch(`${URL_BACKEND}/api/v1${ruta}`, { method: 'POST', headers: { Authorization: `Bearer ${this.token}` }, body: f })
    if (!r.ok) throw new Error(`POST ${ruta} -> ${r.status}: ${(await r.text()).slice(0, 300)}`)
    return (await r.json()) as T
  }
}
