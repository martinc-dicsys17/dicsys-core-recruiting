import { existsSync, mkdirSync, writeFileSync } from 'node:fs'

import { chromium } from '@playwright/test'

import { ESTADO_SEMILLA, SALIDA, estadoDe, ingresar } from './fixtures'
import { sembrar } from './semilla'
import { URL_FRONTEND, contenedoresE2E, huellaBaseHabitual, levantarStack, sql, verificarAislamiento } from './stack'

export default async function globalSetup(): Promise<void> {
  mkdirSync(SALIDA, { recursive: true })
  writeFileSync(`${SALIDA}/monitor.jsonl`, '') // el registro técnico es de esta corrida
  // Solo para iterar: E2E_REUSAR=1 conserva el stack y los datos de la corrida anterior (hecha con E2E_CONSERVAR_STACK=1).
  if (process.env.E2E_REUSAR === '1' && existsSync(ESTADO_SEMILLA)) return
  const informe: Record<string, unknown> = { inicio: new Date().toISOString() }

  // 1) Huella de SOLO LECTURA de la base habitual (antes) y stack aislado arriba.
  informe.baseHabitualAntes = huellaBaseHabitual()
  levantarStack()

  // 2) Verificación explícita del aislamiento ANTES de sembrar o probar nada.
  const aislamiento = verificarAislamiento()
  informe.aislamiento = aislamiento
  const [candidatosIniciales] = sql('select count(*) from recruiting_candidatos')
  if (candidatosIniciales?.[0] !== '0') throw new Error(`La base E2E no está limpia: ${candidatosIniciales?.[0]} candidatos`)

  // 3) Datos ficticios.
  const semilla = await sembrar()
  writeFileSync(ESTADO_SEMILLA, JSON.stringify(semilla, null, 2))
  const [conteo] = sql('select count(*) from recruiting_candidatos')
  informe.candidatosSembrados = Number(conteo?.[0])

  // 4) Sesión de cada usuario (mismo formulario de login que cualquier persona).
  const navegador = await chromium.launch({ channel: 'msedge' })
  for (const clave of ['admin', 'autorizado', 'sinPermiso', 'externo'] as const) {
    const contexto = await navegador.newContext({ baseURL: URL_FRONTEND })
    const pagina = await contexto.newPage()
    await ingresar(pagina, semilla.usuarios[clave])
    await contexto.storageState({ path: estadoDe(clave) })
    await contexto.close()
  }
  await navegador.close()
  informe.contenedores = contenedoresE2E()
  writeFileSync(`${SALIDA}/entorno.json`, JSON.stringify(informe, null, 2))
}
