import { destinoVolver } from '../candidato-nuevo/validacion'
import type { CandidatoSugerido, DesgloseMatch, FormularioBusqueda, Oportunidad } from './types'

/** Lo que la pantalla anterior mostraba (textos, colores y reglas de formato) para la ficha de una búsqueda. */

export const LISTADO = '/recruiting/oportunidades'
export const MATCH_MINIMO_POR_DEFECTO = 50

/** «Volver»: el destino de origen (`?volver=`, solo rutas internas de Recruiting) o el listado de búsquedas. */
export function destinoAtras(volver: unknown): string {
  const destino = destinoVolver(volver, '')
  // Sin un «volver» válido destinoVolver devuelve el listado de candidatos; acá el de la pantalla es Búsquedas.
  return typeof volver === 'string' && volver.trim() === destino ? destino : LISTADO
}

// Modalidad y prioridad se guardan sin tildes (Hibrido, Critica): se muestran con su etiqueta y una ficha vieja con
// tilde se normaliza al abrirla.
const ETIQUETAS_DATO: Record<string, string> = { Hibrido: 'Híbrido', Critica: 'Crítica' }
export const etiquetaDato = (valor: string): string => ETIQUETAS_DATO[valor] ?? valor
export const sinTildesCatalogo = (valor: string | null | undefined): string =>
  String(valor ?? '')
    .replace('Híbrido', 'Hibrido')
    .replace('Crítica', 'Critica')

const CLASES_ESTADO: Record<string, string> = {
  Abierta: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  'Pre-ingreso': 'bg-sky-50 text-sky-700 border-sky-200',
  Suspendida: 'bg-amber-50 text-amber-700 border-amber-200',
  Ganada: 'bg-indigo-50 text-indigo-700 border-indigo-200',
  Cancelada: 'bg-red-50 text-red-700 border-red-200',
}
export const claseEstado = (estado: string): string => CLASES_ESTADO[estado] ?? ''

const CLASES_ETAPA: Record<string, string> = {
  Postulado: 'bg-sky-50 text-sky-700 border-sky-200',
  Screening: 'bg-amber-50 text-amber-700 border-amber-200',
  'Entrevista RRHH': 'bg-indigo-50 text-indigo-700 border-indigo-200',
  'Entrevista Técnica': 'bg-purple-50 text-purple-700 border-purple-200',
  'Entrevista Cliente': 'bg-pink-50 text-pink-700 border-pink-200',
  Oferta: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  Ingreso: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  Descartados: 'bg-red-50 text-red-700 border-red-200',
  Descartado: 'bg-red-50 text-red-700 border-red-200',
}
export const claseEtapa = (etapa: string): string => CLASES_ETAPA[etapa] ?? ''

export function iniciales(nombre: string | null | undefined): string {
  if (!nombre) return 'C'
  const partes = nombre.trim().split(' ')
  const [a, b] = partes
  if (partes.length >= 2 && a && b) return ((a[0] ?? '') + (b[0] ?? '')).toUpperCase()
  return nombre.substring(0, 2).toUpperCase()
}

/** Fecha sola, DD/MM/AAAA; «—» si no hay. */
export function formatearFecha(valor: string | null | undefined): string {
  if (!valor) return '—'
  const texto = String(valor).trim()
  if (!texto || texto === '—' || texto === '-') return '—'
  const iso = /^(\d{4})-(\d{2})-(\d{2})/.exec(texto)
  if (iso) return `${iso[3]}/${iso[2]}/${iso[1]}`
  if (/^\d{2}\/\d{2}\/\d{4}$/.test(texto)) return texto
  const d = new Date(texto)
  if (!Number.isNaN(d.getTime())) {
    return `${String(d.getDate()).padStart(2, '0')}/${String(d.getMonth() + 1).padStart(2, '0')}/${d.getFullYear()}`
  }
  return texto
}

/**
 * Fecha y hora de asignación: el backend guarda UTC sin zona; se muestra en hora local. Los valores históricos (solo
 * fecha, medianoche exacta) se muestran sin hora.
 */
export function formatearFechaHora(valor: string | null | undefined): string {
  if (!valor) return '—'
  const texto = String(valor).trim()
  if (!texto) return '—'
  const m = /^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2}))?/.exec(texto)
  if (!m) return formatearFecha(texto)
  if (!m[4] || (m[4] === '00' && m[5] === '00' && /^\d{4}-\d{2}-\d{2}[T ]00:00(:00(\.0+)?)?$/.test(texto))) {
    return `${m[3]}/${m[2]}/${m[1]}`
  }
  const d = new Date(/(Z|[+-]\d{2}:?\d{2})$/.test(texto) ? texto : `${texto.replace(' ', 'T')}Z`)
  if (Number.isNaN(d.getTime())) return formatearFecha(texto)
  const p = (n: number) => String(n).padStart(2, '0')
  return `${p(d.getDate())}/${p(d.getMonth() + 1)}/${d.getFullYear()} ${p(d.getHours())}:${p(d.getMinutes())}`
}

export function formularioDesde(d: Oportunidad): FormularioBusqueda {
  return {
    titulo: d.titulo || '',
    puesto: d.puesto || '',
    cliente: d.cliente || '',
    area: d.area || 'Operaciones / IT',
    seniority: d.seniority || 'Senior',
    modalidad: sinTildesCatalogo(d.modalidad) || 'Remoto',
    vacantes: d.vacantes || 1,
    rango: d.rango || '',
    recruiter_nombre: d.recruiter_nombre || '',
    lider_nombre: d.lider_nombre || '',
    estado: d.estado || 'Abierta',
    prioridad: sinTildesCatalogo(d.prioridad) || 'Alta',
    tipo: d.tipo || 'Efectiva',
    skills: [...(d.skills ?? [])],
    habilidades: [...(d.habilidades ?? [])],
    skills_deseadas: [...(d.skills_deseadas ?? [])],
    descripcion: d.descripcion || '',
  }
}

const iguales = (a: string, b: string): boolean => String(a).toLowerCase() === String(b).toLowerCase()

/** Porcentaje de coincidencia de un candidato sugerido (el backend manda los dos nombres del mismo valor). */
export const porcentajeMatch = (c: CandidatoSugerido): number => c.match_porcentaje ?? c.porcentaje_match ?? 0

/** Desglose ponderado de Smart Matching: 70% Skills/Habilidades + 30% Seniority. */
export function desgloseMatch(op: Oportunidad, c: CandidatoSugerido): DesgloseMatch {
  const reqSkills = op.skills ?? []
  const reqHabs = op.habilidades ?? []
  const coincSkills = c.skills_coincidentes ?? []
  const coincHabs = c.habilidades_coincidentes ?? []
  const totReq = reqSkills.length + reqHabs.length
  const totCoinc = coincSkills.length + coincHabs.length
  const senRequerido = String(op.seniority || 'Senior').trim()
  const senCandidato = String(c.seniority || 'Senior').trim()
  const senCoincide = iguales(senRequerido, senCandidato)
  const pctSkills = totReq > 0 ? Math.round((totCoinc / totReq) * 100) : 100
  const aporteSkills = Math.round(pctSkills * 0.7)
  const aporteSeniority = senCoincide ? 30 : 0
  return {
    nombre: c.nombre_completo || c.nombre || 'Candidato',
    senRequerido,
    senCandidato,
    senCoincide,
    aporteSkills,
    aporteSeniority,
    porcentaje: c.match_porcentaje ?? c.porcentaje_match ?? aporteSkills + aporteSeniority,
    totReq,
    totCoinc,
    reqSkills,
    coincSkills,
    faltSkills: reqSkills.filter((s) => !coincSkills.some((cs) => iguales(cs, s))),
    reqHabs,
    coincHabs,
    faltHabs: reqHabs.filter((h) => !coincHabs.some((ch) => iguales(ch, h))),
    aplicaHabs: reqHabs.length > 0 || coincHabs.length > 0,
  }
}

/** Texto del `title` del porcentaje (tooltip nativo con el detalle del cálculo). */
export function tooltipMatch(op: Oportunidad, c: CandidatoSugerido): string {
  const d = desgloseMatch(op, c)
  const pct = c.match_porcentaje ?? c.porcentaje_match ?? (d.totReq > 0 ? Math.round((d.totCoinc / d.totReq) * 100) : 0)
  const lista = (l: string[]) => l.join(', ') || 'Ninguna'
  let txt =
    'DETALLE SMART MATCHING\n' +
    '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n' +
    `• Skills requeridas (${d.reqSkills.length}): ${lista(d.reqSkills)}\n` +
    `• Skills coincidentes (${d.coincSkills.length}): ${lista(d.coincSkills)}\n` +
    `• Skills faltantes (${d.faltSkills.length}): ${lista(d.faltSkills)}\n`
  if (d.aplicaHabs) {
    txt +=
      `• Habilidades requeridas (${d.reqHabs.length}): ${lista(d.reqHabs)}\n` +
      `• Habilidades coincidentes (${d.coincHabs.length}): ${lista(d.coincHabs)}\n` +
      `• Habilidades faltantes (${d.faltHabs.length}): ${lista(d.faltHabs)}\n`
  }
  txt +=
    '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n' +
    `• Fórmula: (${d.totCoinc} coincidentes / ${d.totReq} requeridas) × 100\n` +
    `• Resultado final: ${pct}% match`
  return txt
}
