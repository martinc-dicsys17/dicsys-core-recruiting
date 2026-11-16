import { readFileSync, writeFileSync } from 'node:fs'

import { SALIDA } from './fixtures'
import { bajarStack, contenedoresE2E, huellaBaseHabitual } from './stack'

/** Baja el stack E2E (la base vive en tmpfs: se borra sola) y deja constancia de que la base habitual no cambió. */
export default async function globalTeardown(): Promise<void> {
  const archivo = `${SALIDA}/entorno.json`
  let informe: Record<string, unknown> = {}
  try {
    informe = JSON.parse(readFileSync(archivo, 'utf8')) as Record<string, unknown>
  } catch {
    // el setup falló antes de escribir el informe: igual se baja el stack
  }
  informe.baseHabitualDespues = huellaBaseHabitual()
  informe.baseHabitualSinCambios = informe.baseHabitualAntes === informe.baseHabitualDespues
  if (process.env.E2E_CONSERVAR_STACK !== '1') bajarStack()
  informe.contenedoresAlTerminar = contenedoresE2E()
  writeFileSync(archivo, JSON.stringify(informe, null, 2))
}
