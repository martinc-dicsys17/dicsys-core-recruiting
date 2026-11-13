import { PERSONAS_DEMO } from '../demo/blacklist.demo-data'
import type { MotivoBlacklist, PersonaBlacklist } from '../types'

/**
 * Catálogo de motivos: viene del backend (tabla recruiting_motivos_blacklist), por el proxy /api/v1 de Flask,
 * que agrega el token de la sesión. No hay textos fijos.
 */
export async function listarMotivos(): Promise<MotivoBlacklist[]> {
  const respuesta = await fetch('/api/v1/recruiting/blacklist/motivos', { headers: { Accept: 'application/json' } })
  if (!respuesta.ok) throw new Error('No se pudieron cargar los motivos.')
  return (await respuesta.json()) as MotivoBlacklist[]
}

/**
 * Contrato de acceso a datos de Blacklist. Desde esta pantalla solo se consulta el listado y se
 * reactiva una persona (se la quita de Blacklist); las altas y modificaciones se hacen desde
 * otras pantallas (principalmente la ficha del candidato).
 *
 * La pantalla solo conoce esta interfaz: cuando exista el endpoint real se agrega una
 * implementacion HTTP (via el proxy /api/v1 de Flask) y se cambia la exportacion de abajo,
 * sin tocar los componentes.
 */
export interface BlacklistRepository {
  listar(): Promise<PersonaBlacklist[]>
  reactivar(id: string): Promise<void>
}

/** Clave de localStorage con los ids de las personas reactivadas en la demostracion. */
export const CLAVE_REACTIVADAS_DEMO = 'dicsys.blacklist.demo.reactivadas'

function leerReactivadas(): Set<string> {
  try {
    const valor: unknown = JSON.parse(localStorage.getItem(CLAVE_REACTIVADAS_DEMO) ?? '[]')
    return new Set(Array.isArray(valor) ? valor.filter((id): id is string => typeof id === 'string') : [])
  } catch {
    return new Set()
  }
}

/**
 * Implementacion de DEMOSTRACION: datos ficticios, sin llamar al backend.
 * Las reactivaciones se guardan en el localStorage de este navegador, por lo que se mantienen
 * al recargar o volver a entrar. Para restaurar el listado completo, borrar esa clave.
 */
const repositorioDemo: BlacklistRepository = {
  listar() {
    const reactivadas = leerReactivadas()
    const vigentes = PERSONAS_DEMO.filter((p) => !reactivadas.has(p.id)).map((p) => ({ ...p }))
    return new Promise((resolver) => window.setTimeout(() => resolver(vigentes), 350))
  },
  reactivar(id) {
    try {
      localStorage.setItem(CLAVE_REACTIVADAS_DEMO, JSON.stringify([...leerReactivadas().add(id)]))
      return Promise.resolve()
    } catch {
      return Promise.reject(new Error('No se pudo guardar la reactivación en este navegador.'))
    }
  },
}

export const blacklistRepository: BlacklistRepository = repositorioDemo
