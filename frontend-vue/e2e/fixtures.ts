import { appendFileSync, mkdirSync, readFileSync } from 'node:fs'
import path from 'node:path'

import { test as base, expect, type Page, type Request } from '@playwright/test'

export { expect }

export const SALIDA = path.resolve(import.meta.dirname, '.salida')
export const ESTADO_SEMILLA = path.join(SALIDA, 'semilla.json')

/** Datos sembrados por el globalSetup (ids y credenciales ficticias). */
export interface Semilla {
  usuarios: { admin: Credencial; autorizado: Credencial; sinPermiso: Credencial; externo: Credencial }
  candidatos: Record<string, { id: string; nombre: string; apellido: string; email: string }>
  busquedas: Record<string, { id: string; titulo: string }>
  total: number
}
export interface Credencial {
  email: string
  password: string
  estado: string
}
export const semilla = (): Semilla => JSON.parse(readFileSync(ESTADO_SEMILLA, 'utf8')) as Semilla

interface Evento {
  prueba: string
  tipo: 'console' | 'pageerror' | 'http'
  detalle: string
}
const LOG = path.join(SALIDA, 'monitor.jsonl')

/**
 * Monitor técnico de cada prueba: errores de consola, excepciones de la página y respuestas HTTP con error. Todo se
 * registra en .salida/monitor.jsonl (para el informe). Lo que no esté permitido explícitamente hace fallar la prueba.
 */
export class Monitor {
  readonly consola: string[] = []
  readonly http: string[] = []
  readonly mutaciones: { metodo: string; url: string; cuerpo: string | null }[] = []
  // El dashboard de Flask (módulo Recibos, ajeno a Candidatos) pide un parcial que da 403 a quien no tiene ese permiso.
  private permitidos: RegExp[] = [/\/recibos\/mis-recibos\/dashboard-partial/]
  constructor(private readonly prueba: string) {}

  /** Errores esperados en esta prueba (por ejemplo un 403 que la prueba provoca a propósito). */
  permitir(...patrones: RegExp[]): void {
    this.permitidos.push(...patrones)
  }
  private esperado(texto: string): boolean {
    return this.permitidos.some((p) => p.test(texto))
  }
  registrar(tipo: Evento['tipo'], detalle: string): void {
    mkdirSync(SALIDA, { recursive: true })
    const permitido = this.esperado(detalle)
    appendFileSync(LOG, `${JSON.stringify({ prueba: this.prueba, tipo, detalle, permitido })}\n`)
    if (permitido) return
    if (tipo === 'http') this.http.push(detalle)
    else this.consola.push(`${tipo}: ${detalle}`)
  }
  alRequest(r: Request): void {
    const m = r.method()
    if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(m)) {
      const cuerpo = r.postData()
      this.mutaciones.push({ metodo: m, url: new URL(r.url()).pathname, cuerpo: cuerpo && cuerpo.length < 5000 ? cuerpo : null })
    }
  }
  /** Mutaciones al backend/Flask (sin el ruido de la sesión) cuya URL cumple el patrón. */
  mutacionesDe(patron: RegExp): { metodo: string; url: string; cuerpo: string | null }[] {
    return this.mutaciones.filter((m) => patron.test(`${m.metodo} ${m.url}`))
  }
}

type Fixtures = { monitor: Monitor }

export const test = base.extend<Fixtures>({
  monitor: [
    async ({ page }, use, info) => {
      const monitor = new Monitor(info.titlePath.join(' > '))
      page.on('console', (m) => {
        // «Failed to load resource» repite lo que ya se registra como respuesta HTTP con error.
        if (m.type() === 'error' && !m.text().startsWith('Failed to load resource')) monitor.registrar('console', `${m.text()} @ ${m.location().url}`)
      })
      page.on('pageerror', (e) => monitor.registrar('pageerror', String(e)))
      page.on('response', (r) => {
        if (r.status() >= 400) monitor.registrar('http', `${r.status()} ${r.request().method()} ${new URL(r.url()).pathname}`)
      })
      page.on('request', (r) => monitor.alRequest(r))
      await use(monitor)
      // Sin errores de consola ni de red que la prueba no haya declarado como esperados.
      expect.soft(monitor.consola, 'errores de consola / excepciones JS').toEqual([])
      expect.soft(monitor.http, 'respuestas HTTP con error').toEqual([])
    },
    { auto: true },
  ],
})

/** Entra con el formulario de login de Flask (el mismo que usa cualquier persona) y espera el dashboard. */
export async function ingresar(page: Page, c: Credencial): Promise<void> {
  await page.goto('/login')
  await page.locator('input[name="email"]').fill(c.email)
  await page.locator('input[name="password"]').fill(c.password)
  await Promise.all([page.waitForURL((u) => !u.pathname.startsWith('/login'), { timeout: 20_000 }), page.locator('form button[type="submit"], form input[type="submit"]').first().click()])
}

export const estadoDe = (clave: keyof Semilla['usuarios']): string => path.join(SALIDA, `estado-${clave}.json`)
