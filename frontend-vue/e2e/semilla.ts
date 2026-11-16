import { ClienteApi, ADMIN } from './api'
import { crearPdf, textoCv } from './archivos'
import type { Semilla } from './fixtures'

/**
 * Datos FICTICIOS de la base E2E: usuarios con distintos permisos, 105 candidatos (para probar la paginación de 20, 50
 * y 100) con atributos repartidos de forma determinística, y búsquedas. Nada de esto toca la base habitual.
 */
const CLAVE = 'E2e-Usuario-2026!'
const NOMBRES = ['Ana', 'Bruno', 'Carla', 'Diego', 'Elena', 'Fabian', 'Gala', 'Hugo', 'Ines', 'Julian', 'Karen', 'Leo', 'Mara', 'Nico', 'Olga', 'Pablo', 'Rita', 'Sergio', 'Tamara', 'Ulises']
const APELLIDOS = ['Acosta', 'Benitez', 'Cabrera', 'Duarte', 'Escobar', 'Funes', 'Gimenez', 'Herrera', 'Ibarra', 'Juarez', 'Lopez', 'Molina']
const SENIORITY = ['Trainee', 'Junior', 'Semi Senior', 'Senior']
const PUESTOS = ['Desarrollador Backend', 'QA Tester / Automation', 'Desarrollador Frontend', 'DevOps Engineer']
export const TOTAL_CANDIDATOS_MASIVOS = 105

interface Skill {
  nombre: string
  categoria?: string | null
}

export async function sembrar(): Promise<Semilla> {
  const admin = await ClienteApi.ingresar(ADMIN.email, ADMIN.password)

  // ---- Grupos y usuarios ----
  const permisos = (...m: string[]) => ({ permisos: m.map((modulo) => ({ modulo, tiene_acceso: true })) })
  const grupo = async (nombre: string, modulos: string[]) => {
    const g = await admin.post<{ id: string }>('/permisos/grupos', { nombre, descripcion: `E2E ${nombre}` })
    await admin.put(`/permisos/grupos/${g.id}/permisos`, permisos(...modulos))
    return g.id
  }
  const gRecruiters = await grupo('Recruiters E2E', ['recruiting', 'recruiting.dashboard', 'recruiting.candidatos', 'recruiting.oportunidades', 'recruiting.gestion_busquedas'])
  const gSinPermiso = await grupo('Sin candidatos E2E', ['recruiting', 'recruiting.dashboard'])
  const gExternos = await grupo('EXTERNOS', ['recruiting', 'recruiting.candidatos'])
  const usuario = async (email: string, nombre: string, grupoId: string) => {
    await admin.post('/usuarios', { email, nombre, apellido: 'E2E', password: CLAVE, rol: 'usuario', grupo_ids: [grupoId] })
    return { email, password: CLAVE, estado: nombre }
  }
  const usuarios: Semilla['usuarios'] = {
    admin: { email: ADMIN.email, password: ADMIN.password, estado: 'admin' },
    autorizado: await usuario('reclutador.e2e@dicsys.com', 'Reclutador', gRecruiters),
    sinPermiso: await usuario('sinpermiso.e2e@dicsys.com', 'SinPermiso', gSinPermiso),
    externo: await usuario('externo.e2e@dicsys.com', 'Externo', gExternos),
  }

  // ---- Catálogos reales de la migración ----
  const skills = (await admin.get<Skill[]>('/recruiting/skills')).filter((s) => s.categoria)
  const porCategoria = new Map<string, string[]>()
  for (const s of skills) porCategoria.set(s.categoria as string, [...(porCategoria.get(s.categoria as string) ?? []), s.nombre])
  const cats = [...porCategoria.keys()]
  const pick = (c: number, n: number) => (porCategoria.get(cats[c % cats.length] as string) ?? []).slice(0, n)

  // ---- Candidatos ----
  const candidatos: Semilla['candidatos'] = {}
  const crear = async (clave: string, datos: Record<string, unknown>) => {
    const c = await admin.post<{ id: string; nombre: string; apellido: string; email: string }>('/recruiting/candidatos', datos)
    candidatos[clave] = { id: c.id, nombre: c.nombre, apellido: c.apellido, email: c.email }
    return c
  }

  // Candidatos con datos completos, vacíos y estados particulares (para la ficha y las acciones)
  await crear('completo', {
    nombre: 'Camila', apellido: 'Completa', email: 'camila.completa@example.com', telefono: '+5493515550101', dni: '30111222',
    fecha_nacimiento: '1990-05-17', linkedin_url: 'https://linkedin.com/in/camila-completa', provincia_id: 1, ciudad_id: 1,
    headline: 'Desarrollador Backend', seniority: 'Semi Senior', modalidad: 'Híbrido', pretension_salarial: 1500000, moneda: 'ARS',
    moneda_pretension: 'ARS', fuente: 'LinkedIn', skills: [...pick(0, 3), ...pick(1, 2)], habilidades: ['Liderazgo', 'Trabajo en equipo'],
  })
  await crear('usd', {
    nombre: 'Dario', apellido: 'Dolar', email: 'dario.dolar@example.com', telefono: '+5491155550102', provincia_id: 2,
    headline: 'DevOps Engineer', seniority: 'Senior', modalidad: 'Remoto', pretension_salarial: 4200, moneda: 'USD', moneda_pretension: 'USD', skills: pick(1, 2),
  })
  await crear('vacio', { nombre: 'Vera', apellido: 'Vacia', email: 'vera.vacia@example.com' })
  await crear('rechazado', { nombre: 'Rolando', apellido: 'Rechazado', email: 'rolando.rechazado@example.com', estado: 'Rechazado', skills: pick(2, 1) })
  await crear('sinrespuesta', { nombre: 'Sol', apellido: 'Silencio', email: 'sol.silencio@example.com', estado: 'Sin respuesta' })
  await crear('eliminar1', { nombre: 'Elias', apellido: 'Eliminable', email: 'elias.eliminable@example.com', seniority: 'Junior' })
  await crear('eliminar2', { nombre: 'Emma', apellido: 'Eliminable', email: 'emma.eliminable@example.com', seniority: 'Junior' })
  await crear('elegible', {
    nombre: 'Elisa', apellido: 'Elegible', email: 'elisa.elegible@example.com', seniority: 'Semi Senior', headline: 'Desarrollador Backend',
    skills: ['Python', 'PostgreSQL'], telefono: '+5493515550103',
  })
  await crear('pipeline', {
    nombre: 'Pedro', apellido: 'Pipeline', email: 'pedro.pipeline@example.com', seniority: 'Semi Senior', headline: 'Desarrollador Backend',
    skills: ['Python', 'PostgreSQL'], telefono: '+5493515550104',
  })
  await crear('cv', { nombre: 'Cecilia', apellido: 'ConCV', email: 'cecilia.concv@example.com', seniority: 'Junior', skills: pick(0, 1) })

  // 105 candidatos «de relleno» con atributos repartidos para filtros y paginación
  for (let i = 1; i <= TOTAL_CANDIDATOS_MASIVOS; i++) {
    const n = String(i).padStart(3, '0')
    await admin.post('/recruiting/candidatos', {
      nombre: `${NOMBRES[i % NOMBRES.length]}${n}`,
      apellido: APELLIDOS[i % APELLIDOS.length],
      email: `e2e.masivo${n}@example.com`,
      telefono: i % 3 === 0 ? `+54351555${n}` : null,
      provincia_id: (i % 3) + 1,
      seniority: SENIORITY[i % SENIORITY.length],
      headline: PUESTOS[i % PUESTOS.length],
      modalidad: ['Remoto', 'Híbrido', 'Presencial'][i % 3],
      skills: pick(i, 1 + (i % 4)),
    })
  }

  // CV adjunto de uno (descarga) y búsquedas
  await admin.subirArchivo(`/recruiting/candidatos/${candidatos.cv?.id}/cv`, 'cv-cecilia.pdf', crearPdf(textoCv({ nombre: 'Cecilia', apellido: 'ConCV', email: 'cecilia.concv@example.com' })))
  const busqueda = async (clave: string, datos: Record<string, unknown>) => {
    const b = await admin.post<{ id: string; titulo: string }>('/recruiting/oportunidades', datos)
    busquedas[clave] = { id: b.id, titulo: b.titulo }
  }
  const busquedas: Semilla['busquedas'] = {}
  await busqueda('python', { cliente: 'Cliente E2E', titulo: 'Backend Python E2E', estado: 'Abierta', seniority: 'Semi Senior', modalidad: 'Remoto', vacantes: 1, skills: ['Python', 'PostgreSQL', 'Docker'], habilidades: [], skills_deseadas: [] })
  await busqueda('sin-coincidencia', { cliente: 'Cliente E2E', titulo: 'Disenio Grafico E2E', estado: 'Abierta', seniority: 'Trainee', modalidad: 'Remoto', vacantes: 1, skills: ['Photoshop', 'Illustrator'], habilidades: [], skills_deseadas: [] })
  await busqueda('pipeline', { cliente: 'Cliente E2E', titulo: 'Pipeline E2E', estado: 'Abierta', seniority: 'Semi Senior', modalidad: 'Remoto', vacantes: 1, skills: ['Python'], habilidades: [], skills_deseadas: [] })

  // «Pedro Pipeline» con historial de pipeline (para el botón «Ver detalles»)
  await admin.post(`/recruiting/oportunidades/${busquedas.pipeline?.id}/candidatos`, { candidato_id: candidatos.pipeline?.id })
  await admin.put(`/recruiting/oportunidades/${busquedas.pipeline?.id}/candidatos/${candidatos.pipeline?.id}/etapa`, { etapa_actual: 'Screening' })

  return { usuarios, candidatos, busquedas, total: 10 + TOTAL_CANDIDATOS_MASIVOS }
}
