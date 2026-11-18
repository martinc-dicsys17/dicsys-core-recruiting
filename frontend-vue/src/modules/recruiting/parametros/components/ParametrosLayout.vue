<script setup lang="ts">
import {
  Archive,
  Award,
  Briefcase,
  History,
  Map,
  MapPin,
  ShieldBan,
  Sparkles,
  UserCheck,
  Users,
  type LucideIcon,
} from '@lucide/vue'
import { useSessionStore } from '@/core/stores/session'

interface Pestana {
  clave: string
  ruta: string
  nombre: string
  icono: LucideIcon
}

defineProps<{
  /** Clave de la pestaña de esta pantalla (skills, provincias, archivos-cv...). */
  activa: string
  /** Cantidad que se muestra en la pestaña activa, como en la interfaz anterior. */
  contadores?: Record<string, number>
}>()

const sesion = useSessionStore()

const PESTANAS: Pestana[] = [
  { clave: 'config', ruta: '/recruiting/parametros', nombre: 'Porcentaje de Aceptación', icono: Sparkles },
  { clave: 'skills', ruta: '/recruiting/parametros/skills', nombre: 'Skills / Tecnologías', icono: Award },
  { clave: 'habilidades', ruta: '/recruiting/parametros/habilidades', nombre: 'Habilidades / Competencias', icono: Award },
  { clave: 'provincias', ruta: '/recruiting/parametros/provincias', nombre: 'Provincias', icono: Map },
  { clave: 'ciudades', ruta: '/recruiting/parametros/ciudades', nombre: 'Ciudades', icono: MapPin },
  { clave: 'lideres', ruta: '/recruiting/parametros/lideres', nombre: 'Líderes / Hiring Managers', icono: UserCheck },
  { clave: 'reclutadores', ruta: '/recruiting/parametros/reclutadores', nombre: 'Reclutadores', icono: Users },
  { clave: 'perfiles', ruta: '/recruiting/parametros/perfiles-profesionales', nombre: 'Perfiles profesionales', icono: Briefcase },
  { clave: 'motivos', ruta: '/recruiting/parametros/motivos-blacklist', nombre: 'Motivos de Blacklist', icono: ShieldBan },
  { clave: 'archivos', ruta: '/recruiting/parametros/archivos-cv', nombre: 'Archivos de CV', icono: Archive },
  { clave: 'historial', ruta: '/recruiting/parametros/historial-cargas-cv', nombre: 'Historial de cargas de CV', icono: History },
]

/** La pestaña del historial solo se ofrece a administradores (el backend lo vuelve a validar). */
const pestanas = PESTANAS.filter((p) => p.clave !== 'historial' || sesion.esAdmin)
</script>

<template>
  <div class="animate-fade-in space-y-6">
    <div class="space-y-4">
      <div class="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 class="text-3xl font-bold text-dark-900">Parámetros</h1>
          <p class="mt-1 text-sm text-dark-500">Configuración y catálogos maestros del módulo de Recruiting</p>
        </div>
      </div>

      <div class="flex flex-wrap items-stretch gap-x-1 border-b border-dark-200/80 pt-2" data-testid="parametros-pestanas">
        <RouterLink
          v-for="pestana in pestanas"
          :key="pestana.clave"
          :to="pestana.ruta"
          class="inline-flex flex-1 basis-0 items-center justify-center gap-1 border-b-2 px-1.5 py-2 text-center text-[11px] leading-tight transition-colors"
          :class="
            pestana.clave === activa
              ? 'border-primary-600 font-bold text-primary-600'
              : 'border-transparent font-medium text-dark-500 hover:border-dark-300 hover:text-dark-700'
          "
        >
          <component :is="pestana.icono" class="h-3 w-3 shrink-0" />
          <span>{{ pestana.nombre }}</span>
          <span
            v-if="pestana.clave === activa && contadores?.[pestana.clave] !== undefined"
            class="shrink-0 rounded-full bg-primary-50 px-1 py-0.5 text-[10px] font-semibold text-primary-700"
          >
            {{ contadores[pestana.clave] }}
          </span>
        </RouterLink>
      </div>
    </div>

    <slot />
  </div>
</template>
