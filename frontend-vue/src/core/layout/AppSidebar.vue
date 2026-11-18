<script setup lang="ts">
import { ChevronDown, LayoutDashboard } from '@lucide/vue'
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { BASE_SPA, type MenuGrupo, type MenuItem } from '@/core/bootstrap'
import { useSessionStore } from '@/core/stores/session'

import { iconoDeMenu } from './menuIcons'

const props = defineProps<{ colapsado: boolean }>()
const emit = defineEmits<{ expandir: [] }>()

const sesion = useSessionStore()
const route = useRoute()
const router = useRouter()

/** Ruta interna del router para un item Vue (su url llega con el prefijo de la SPA). */
function rutaInterna(item: MenuItem): string {
  return item.url?.slice(BASE_SPA.length) || '/'
}

function esActivo(item: MenuItem): boolean {
  return item.vue && item.url !== null && route.path === rutaInterna(item)
}

/**
 * Item de una pantalla ya migrada a Vue que sigue en el menu de siempre (por ejemplo «Candidatos»): su url es la de
 * Flask y el router de la SPA tiene una ruta para ese mismo camino. Se muestra en verde, como los items Vue, y mas
 * marcado mientras se esta en esa pantalla o en una dependiente (la ficha de un candidato).
 */
function rutaDelItem(item: MenuItem): string | null {
  if (item.vue || item.url === null) return null
  const ruta = new URL(item.url, window.location.origin).pathname
  return ruta === '/' ? null : ruta
}

function esMigrado(item: MenuItem): boolean {
  const ruta = rutaDelItem(item)
  return ruta !== null && router.resolve(ruta).name !== 'no-encontrada'
}

/**
 * Activo si la pantalla actual es la del ítem (misma ruta del router, aunque Flask arme otra URL para el mismo
 * endpoint) o una dependiente de su dirección. Una pantalla puede fijar qué ítem resalta con `meta.itemMenu`: el
 * Pipeline de una búsqueda cuelga de /recruiting/oportunidades pero resalta «Pipeline», no «Búsquedas».
 */
function esMigradoActivo(item: MenuItem): boolean {
  const ruta = rutaDelItem(item)
  if (ruta === null || !esMigrado(item)) return false
  const destino = router.resolve(ruta).name
  if (route.meta.itemMenu) return destino === route.meta.itemMenu
  return destino === route.name || route.path === ruta || route.path.startsWith(`${ruta}/`)
}

function grupoActivo(grupo: MenuGrupo): boolean {
  return grupo.items.some((item) => esActivo(item) || esMigradoActivo(item))
}

const abiertos = ref(new Set(sesion.menus.filter(grupoActivo).map((g) => g.codigo)))

function alternar(grupo: MenuGrupo): void {
  if (props.colapsado) {
    emit('expandir')
    abiertos.value.add(grupo.codigo)
    return
  }
  if (!abiertos.value.delete(grupo.codigo)) abiertos.value.add(grupo.codigo)
}
</script>

<template>
  <aside
    class="fixed top-[68px] left-0 z-20 flex h-[calc(100vh-68px)] flex-col overflow-hidden border-r border-dark-200/50 bg-white transition-all duration-300"
    :class="colapsado ? 'w-[72px]' : 'w-72'"
  >
    <nav class="flex-1 space-y-1 overflow-x-hidden overflow-y-auto p-3" aria-label="Menú principal">
      <p v-show="!colapsado" class="mb-3 px-3 text-xs font-semibold tracking-wider text-dark-400 uppercase">
        Principal
      </p>
      <a
        :href="sesion.enlaces.inicio"
        class="group flex items-center rounded-xl py-2.5 text-dark-600 transition-all duration-200 hover:bg-dark-50"
        :class="colapsado ? 'justify-center px-2' : 'px-3'"
      >
        <span
          class="shrink-0 rounded-xl bg-dark-100 p-2.5 transition-colors group-hover:bg-primary-100"
          :class="{ 'mr-3': !colapsado }"
        >
          <LayoutDashboard class="h-5 w-5 text-dark-500 group-hover:text-primary-600" />
        </span>
        <span v-show="!colapsado" class="font-medium whitespace-nowrap">Dashboard</span>
      </a>

      <p
        v-if="sesion.menus.length"
        v-show="!colapsado"
        class="mt-6 mb-3 px-3 text-xs font-semibold tracking-wider text-dark-400 uppercase"
      >
        Módulos
      </p>

      <div v-for="grupo in sesion.menus" :key="grupo.codigo" class="space-y-1">
        <button
          type="button"
          class="group flex w-full items-center rounded-xl py-2.5 transition-all duration-200"
          :class="[
            colapsado ? 'justify-center px-2' : 'px-3',
            grupoActivo(grupo) ? 'bg-primary-50 text-primary-700' : 'text-dark-600 hover:bg-dark-50',
          ]"
          :aria-expanded="abiertos.has(grupo.codigo) && !colapsado"
          :title="colapsado ? grupo.nombre : undefined"
          @click="alternar(grupo)"
        >
          <span
            class="shrink-0 rounded-xl p-2.5 transition-colors"
            :class="[
              { 'mr-3': !colapsado },
              grupoActivo(grupo) ? 'bg-primary-100' : 'bg-dark-100 group-hover:bg-primary-100',
            ]"
          >
            <component
              :is="iconoDeMenu(grupo.icono, 'grupo')"
              class="h-5 w-5"
              :class="grupoActivo(grupo) ? 'text-primary-600' : 'text-dark-500 group-hover:text-primary-600'"
            />
          </span>
          <span v-show="!colapsado" class="flex-1 text-left font-medium whitespace-nowrap">{{ grupo.nombre }}</span>
          <ChevronDown
            v-show="!colapsado"
            class="h-4 w-4 text-dark-400 transition-transform duration-200"
            :class="{ 'rotate-180': abiertos.has(grupo.codigo) }"
          />
        </button>

        <div v-show="abiertos.has(grupo.codigo) && !colapsado" class="ml-4 space-y-1">
          <template v-for="item in grupo.items" :key="item.nombre">
            <!--
              Estandar visual de pantallas migradas a Vue: fondo verde muy suave, linea verde
              a la izquierda y etiqueta "VUE". Debe coincidir con el item equivalente de core/base.html.
            -->
            <RouterLink
              v-if="item.vue && item.url"
              :to="rutaInterna(item)"
              class="flex items-center rounded-lg px-3 py-2 shadow-[inset_2px_0_0_0_#34d399] transition-all duration-200"
              :class="
                esActivo(item)
                  ? 'bg-emerald-100/80 text-emerald-900'
                  : 'bg-emerald-50/70 text-dark-600 hover:bg-emerald-100/70 hover:text-dark-800'
              "
              :aria-current="esActivo(item) ? 'page' : undefined"
            >
              <component :is="iconoDeMenu(item.icono, 'item')" class="mr-3 h-4 w-4 text-emerald-600" />
              <span class="text-sm" :class="esActivo(item) ? 'font-bold' : 'font-medium'">{{ item.nombre }}</span>
            </RouterLink>
            <!-- Pantalla ya migrada a Vue (item de siempre): mismo verde que los items Vue -->
            <a
              v-else-if="item.url"
              :href="item.url"
              class="group flex items-center rounded-lg px-3 py-2 transition-all duration-200"
              :class="
                esMigrado(item)
                  ? [
                      'shadow-[inset_2px_0_0_0_#34d399]',
                      esMigradoActivo(item)
                        ? 'bg-emerald-100/80 text-emerald-900'
                        : 'bg-emerald-50/70 text-dark-600 hover:bg-emerald-100/70 hover:text-dark-800',
                    ]
                  : 'text-dark-500 hover:bg-dark-50 hover:text-dark-700'
              "
              :aria-current="esMigradoActivo(item) ? 'page' : undefined"
            >
              <component
                :is="iconoDeMenu(item.icono, 'item')"
                class="mr-3 h-4 w-4"
                :class="esMigrado(item) ? 'text-emerald-600' : 'text-dark-400 group-hover:text-dark-600'"
              />
              <span class="text-sm" :class="esMigradoActivo(item) ? 'font-bold' : 'font-medium'">{{ item.nombre }}</span>
            </a>
            <span v-else class="flex cursor-not-allowed items-center rounded-lg px-3 py-2 text-dark-400">
              <component :is="iconoDeMenu(item.icono, 'item')" class="mr-3 h-4 w-4" />
              <span class="text-sm">{{ item.nombre }}</span>
              <span class="ml-auto rounded bg-dark-100 px-2 py-0.5 text-xs">Próx.</span>
            </span>
          </template>
        </div>
      </div>
    </nav>
  </aside>
</template>
