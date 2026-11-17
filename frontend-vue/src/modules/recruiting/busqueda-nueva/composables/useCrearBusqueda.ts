import { useMutation } from '@tanstack/vue-query'

import { nuevaBusquedaRepository as repo } from '../api/nueva-busqueda.repository'
import type { BusquedaCreate, FormularioBusqueda } from '../types'

/**
 * Cuerpo del alta, igual al que armaba la pantalla anterior y reenviaba Flask: lo vacío no se manda (el backend aplica
 * sus valores predeterminados), líder y reclutador viajan en null si no se eligieron y las vacantes valen 1 por defecto.
 */
export function armarAlta(f: FormularioBusqueda): BusquedaCreate {
  const texto = (v: string) => v.trim()
  return {
    titulo: texto(f.titulo),
    cliente: texto(f.cliente),
    estado: 'Abierta',
    ...(texto(f.puesto) && { puesto: texto(f.puesto) }),
    ...(texto(f.seniority) && { seniority: texto(f.seniority) }),
    ...(texto(f.modalidad) && { modalidad: texto(f.modalidad) }),
    ...(texto(f.rango) && { rango: texto(f.rango) }),
    ...(texto(f.prioridad) && { prioridad: texto(f.prioridad) }),
    ...(texto(f.tipo) && { tipo: texto(f.tipo) }),
    lider_nombre: texto(f.hm) || null,
    recruiter_nombre: texto(f.reclutador) || null,
    vacantes: parseInt(String(f.vacantes), 10) || 1,
    skills: [...f.skills],
    habilidades: [...f.habilidades],
    skills_deseadas: [...f.skills_deseadas],
    descripcion: texto(f.descripcion) || null,
  }
}

export function useCrearBusqueda() {
  return useMutation({ mutationFn: (formulario: FormularioBusqueda) => repo.crear(armarAlta(formulario)) })
}
