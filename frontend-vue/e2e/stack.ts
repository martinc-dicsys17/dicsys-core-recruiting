import { execFileSync } from 'node:child_process'
import path from 'node:path'

/**
 * Stack E2E aislado (docker-compose.e2e.yml, proyecto «dicsys-core-e2e»): base propia en tmpfs, sin los datos ni las
 * credenciales del stack habitual. Todo lo que toca la base de pruebas sale de acá.
 */
export const RAIZ = path.resolve(import.meta.dirname, '..', '..')
export const COMPOSE = ['compose', '-f', path.join(RAIZ, 'docker-compose.e2e.yml')]
export const URL_FRONTEND = 'http://127.0.0.1:18080'
export const URL_BACKEND = 'http://127.0.0.1:18000'
export const PROYECTO = 'dicsys-core-e2e'

function docker(args: string[], opciones: { input?: string; timeout?: number } = {}): string {
  return execFileSync('docker', args, {
    cwd: RAIZ,
    encoding: 'utf8',
    input: opciones.input,
    timeout: opciones.timeout ?? 600_000,
    stdio: ['pipe', 'pipe', 'pipe'],
  })
}

/** Siempre desde cero (se baja lo que haya y se borra su base): cada corrida arranca con una base limpia. */
export const levantarStack = () => {
  docker([...COMPOSE, 'down', '-v', '--remove-orphans'])
  return docker([...COMPOSE, 'up', '-d', '--wait'])
}
export const bajarStack = () => docker([...COMPOSE, 'down', '-v', '--remove-orphans'])

/** Ejecuta SQL en la base AISLADA y devuelve las filas (separadas por | , una por línea). */
export function sql(consulta: string): string[][] {
  const salida = docker([...COMPOSE, 'exec', '-T', 'e2e-db', 'psql', '-U', 'e2e', '-d', 'dicsys_core_e2e', '-At', '-c', consulta])
  return salida
    .split('\n')
    .map((l) => l.trim())
    .filter(Boolean)
    .map((l) => l.split('|'))
}

/**
 * Comprueba, ANTES de sembrar o probar nada, que la aplicación escribe en la base aislada: el backend apunta al
 * contenedor e2e-db, y esa base es la de pruebas (nombre, usuario y contenedor propios del proyecto E2E).
 */
export function verificarAislamiento(): { urlBackend: string; baseActual: string; contenedores: string[] } {
  const urlBackend = docker([...COMPOSE, 'exec', '-T', 'e2e-backend', 'printenv', 'DATABASE_URL']).trim()
  if (!urlBackend.includes('@e2e-db:5432/dicsys_core_e2e')) {
    throw new Error(`El backend E2E NO apunta a la base aislada: ${urlBackend}`)
  }
  const baseActual = sql('select current_database()')[0]?.[0] ?? ''
  if (baseActual !== 'dicsys_core_e2e') throw new Error(`Base inesperada: ${baseActual}`)
  const contenedores = docker(['ps', '--filter', `label=com.docker.compose.project=${PROYECTO}`, '--format', '{{.Names}}'])
    .split('\n')
    .map((l) => l.trim())
    .filter(Boolean)
  if (contenedores.some((c) => !c.startsWith('dicsys-core-e2e-'))) throw new Error('Contenedores ajenos al proyecto E2E')
  return { urlBackend, baseActual, contenedores }
}

/**
 * Huella de SOLO LECTURA de la base habitual (contenedor del stack de desarrollo) para demostrar que las pruebas no la
 * tocan: cantidad de candidatos, última modificación y contadores de inserciones/modificaciones/bajas.
 */
export function huellaBaseHabitual(): string | null {
  try {
    const usuario = docker(['exec', 'corerecruit-postgresql-1', 'printenv', 'POSTGRES_USER']).trim()
    const base = docker(['exec', 'corerecruit-postgresql-1', 'printenv', 'POSTGRES_DB']).trim()
    const consulta =
      "select (select count(*) from recruiting_candidatos) || ' candidatos; max(updated_at)=' || " +
      "coalesce((select max(updated_at)::text from recruiting_candidatos),'-') || '; ins/upd/del=' || " +
      "(select n_tup_ins||'/'||n_tup_upd||'/'||n_tup_del from pg_stat_user_tables where relname='recruiting_candidatos')"
    return docker(['exec', 'corerecruit-postgresql-1', 'psql', '-U', usuario, '-d', base, '-At', '-c', consulta]).trim()
  } catch {
    return null
  }
}

/** Contenedores del proyecto E2E que siguen en pie (para comprobar que no queda nada al terminar). */
export function contenedoresE2E(): string[] {
  return docker(['ps', '-a', '--filter', `label=com.docker.compose.project=${PROYECTO}`, '--format', '{{.Names}}'])
    .split('\n')
    .map((l) => l.trim())
    .filter(Boolean)
}
