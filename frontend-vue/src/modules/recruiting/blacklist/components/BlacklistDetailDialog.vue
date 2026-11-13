<script setup lang="ts">
import { CalendarDays, ClipboardList, FileText, IdCard, Mail, Phone, ShieldBan, TriangleAlert, UserCheck, UserRound } from '@lucide/vue'
import Button from 'primevue/button'
import Dialog from 'primevue/dialog'
import Tag from 'primevue/tag'
import { computed, ref, watch } from 'vue'

import { ESTILO_MOTIVO, formatearFecha, iniciales } from '../presentacion'
import type { PersonaBlacklist } from '../types'

/** Persona a mostrar; null = cerrado. El detalle no permite modificar el registro: solo reactivar a la persona. */
const persona = defineModel<PersonaBlacklist | null>('persona', { required: true })
const emit = defineEmits<{ reactivar: [persona: PersonaBlacklist] }>()

// Se conserva la ultima persona para que el contenido no desaparezca durante la animacion de cierre.
const mostrada = ref<PersonaBlacklist | null>(persona.value)
watch(persona, (nueva) => {
  if (nueva) mostrada.value = nueva
})

// Confirmacion previa a reactivar: solo al confirmar se emite el evento hacia la pagina.
const confirmando = ref(false)
const confirmacionAbierta = ref(false)
watch(persona, () => {
  confirmacionAbierta.value = false
  confirmando.value = false
})

function confirmarReactivacion(): void {
  if (confirmando.value || !mostrada.value) return
  confirmando.value = true
  confirmacionAbierta.value = false
  emit('reactivar', mostrada.value)
}

const visible = computed({
  get: () => persona.value !== null,
  set: (abierto) => {
    if (!abierto) persona.value = null
  },
})

// Modal blanco con detalles y acentos en bordó y negro
const ESTILOS_DIALOG = {
  mask: { class: 'backdrop-blur-xs bg-dark-900/40' },
  root: { class: 'overflow-hidden rounded-2xl bg-white shadow-2xl border border-dark-200' },
  header: { class: 'border-b border-dark-100 bg-white px-6 py-4 text-dark-900' },
  pcCloseButton: { root: { class: 'text-dark-400 hover:bg-dark-100 hover:text-dark-700 rounded-xl' } },
  content: { class: 'px-6 py-5 bg-white' },
  footer: { class: 'border-t border-dark-100 bg-dark-50/60 px-6 py-3 flex items-center justify-end gap-3' },
}

// Confirmacion: mismo estilo, con la linea bajo el titulo mas visible.
const ESTILOS_CONFIRMACION = {
  ...ESTILOS_DIALOG,
  header: { class: 'border-b border-dark-300 bg-white px-6 py-4 text-dark-900' },
}

const GRUPO = 'rounded-xl border border-dark-200/80 bg-dark-50/50 p-4'
const TITULO_GRUPO = 'flex items-center gap-2 text-[11px] font-bold tracking-[0.08em] text-dark-500 uppercase'
const ETIQUETA = 'text-xs text-dark-500'
const VALOR = 'mt-0.5 text-sm font-semibold text-dark-900'
</script>

<template>
  <Dialog
    v-model:visible="visible"
    modal
    dismissable-mask
    block-scroll
    aria-labelledby="blacklist-detalle-titulo"
    :close-on-escape="!confirmacionAbierta"
    :draggable="false"
    :style="{ width: '70rem', maxWidth: '96vw' }"
    :pt="ESTILOS_DIALOG"
  >
    <template v-if="mostrada" #header>
      <div class="flex min-w-0 items-center gap-4">
        <span
          class="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl bg-linear-to-br from-bordo-700 to-dark-900 text-lg font-bold tracking-wide text-white shadow-sm ring-1 ring-dark-900/10"
        >
          {{ iniciales(mostrada) }}
        </span>
        <div class="min-w-0">
          <h2 id="blacklist-detalle-titulo" class="truncate text-[1.7rem] leading-tight font-extrabold tracking-tight text-dark-900">
            {{ mostrada.apellido }}, {{ mostrada.nombre }}
          </h2>
          <p
            class="mt-1.5 inline-flex items-center gap-1.5 rounded-full bg-bordo-50 border border-bordo-200 px-2.5 py-0.5 text-xs font-semibold text-bordo-800"
          >
            <ShieldBan class="h-3.5 w-3.5 text-bordo-600" />Persona no entrevistable
          </p>
        </div>
      </div>
    </template>

    <div v-if="mostrada" class="grid grid-cols-[minmax(0,3fr)_minmax(0,2fr)] items-start gap-4">
      <!-- Columna izquierda: motivo y observacion -->
      <div class="space-y-4">
      <!-- Tarjeta destacada: Motivo de incorporación (elemento visual principal del modal) -->
      <section
        class="rounded-2xl border border-bordo-200/90 bg-linear-to-br from-bordo-50/80 via-bordo-50/40 to-white p-4 shadow-xs"
      >
        <div class="flex items-center justify-between gap-3">
          <h3 class="flex items-center gap-2 text-xs font-bold tracking-wider text-bordo-800 uppercase">
            <ClipboardList class="h-4 w-4 text-bordo-600" />
            <span>Motivo</span>
          </h3>
          <Tag rounded class="ring-1 ring-inset" :class="ESTILO_MOTIVO.etiqueta">
            <span class="h-1.5 w-1.5 rounded-full" :class="ESTILO_MOTIVO.punto"></span>
            <span>{{ mostrada.motivo }}</span>
          </Tag>
        </div>

        <div class="mt-2">
          <p class="text-2xl sm:text-[1.65rem] font-extrabold tracking-tight text-bordo-900 leading-tight">
            {{ mostrada.motivo }}
          </p>
        </div>
      </section>

      <!-- Sección independiente: OBSERVACIÓN (detalle extenso registrado por el reclutador) -->
      <section
        class="rounded-xl border border-dark-200/80 bg-slate-50/60 p-5 shadow-xs"
      >
        <h3 class="flex items-center gap-2 text-[11px] font-bold tracking-[0.08em] text-dark-500 uppercase">
          <FileText class="h-4 w-4 text-bordo-600" />
          <span>Observación</span>
        </h3>
        <p class="mt-3 text-sm sm:text-[15px] leading-relaxed text-dark-800 font-normal whitespace-pre-line break-words">
          {{ mostrada.observacion || 'Sin observación registrada.' }}
        </p>
      </section>

      </div>

      <!-- Columna derecha: datos personales, contacto y registro -->
      <div class="space-y-4">
      <section :class="GRUPO">
        <h3 :class="TITULO_GRUPO"><IdCard class="h-4 w-4 text-bordo-600" />Datos personales</h3>
        <dl class="mt-3 space-y-3">
          <div>
            <dt :class="ETIQUETA">Nombre completo</dt>
            <dd :class="VALOR">{{ mostrada.nombre }} {{ mostrada.apellido }}</dd>
          </div>
          <div>
            <dt :class="ETIQUETA">Documento</dt>
            <dd :class="[VALOR, 'font-mono text-dark-800']">{{ mostrada.documento || 'Sin documento' }}</dd>
          </div>
        </dl>
      </section>

      <section :class="GRUPO">
        <h3 :class="TITULO_GRUPO"><Mail class="h-4 w-4 text-bordo-600" />Contacto</h3>
        <dl class="mt-3 space-y-3">
          <div>
            <dt :class="ETIQUETA">Email</dt>
            <dd :class="[VALOR, 'break-all text-dark-800']">{{ mostrada.email || 'Sin email' }}</dd>
          </div>
          <div>
            <dt :class="[ETIQUETA, 'flex items-center gap-1']"><Phone class="h-3 w-3" />Teléfono</dt>
            <dd :class="VALOR">{{ mostrada.telefono || 'Sin teléfono' }}</dd>
          </div>
        </dl>
      </section>

      <section :class="GRUPO">
        <h3 :class="TITULO_GRUPO"><CalendarDays class="h-4 w-4 text-bordo-600" />Registro</h3>
        <dl class="mt-3 grid grid-cols-[1.7fr_1fr] gap-3">
          <div>
            <dt :class="ETIQUETA">Fecha de incorporación a Blacklist</dt>
            <dd :class="VALOR">{{ formatearFecha(mostrada.fechaAlta, 'long') }}</dd>
          </div>
          <div>
            <dt :class="[ETIQUETA, 'flex items-center gap-1']"><UserRound class="h-3 w-3" />Registrado por</dt>
            <dd :class="VALOR">{{ mostrada.registradoPor }}</dd>
          </div>
        </dl>
      </section>
      </div>
    </div>

    <template #footer>
      <Button label="Cerrar" severity="secondary" outlined @click="visible = false" />
      <Button
        label="Reactivar persona"
        class="bg-bordo-700! hover:bg-bordo-800! text-white! border-bordo-700! shadow-sm"
        @click="confirmacionAbierta = true"
      >
        <template #icon><UserCheck class="h-4 w-4 mr-1.5" /></template>
      </Button>
    </template>
  </Dialog>

  <!-- Confirmacion de reactivacion -->
  <Dialog
    v-model:visible="confirmacionAbierta"
    modal
    dismissable-mask
    block-scroll
    :draggable="false"
    :style="{ width: '30rem' }"
    aria-labelledby="blacklist-confirmacion-titulo"
    :pt="ESTILOS_CONFIRMACION"
  >
    <template #header>
      <div class="flex items-center gap-3">
        <span class="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-bordo-50 ring-1 ring-bordo-200">
          <TriangleAlert class="h-5 w-5 text-bordo-700" />
        </span>
        <h2 id="blacklist-confirmacion-titulo" class="text-xl leading-tight font-extrabold tracking-tight text-dark-900">Confirmar reactivacion</h2>
      </div>
    </template>
    <div>
      <p class="text-[15px] font-semibold text-dark-900">¿Está seguro de que desea reactivar a esta persona?</p>
      <p class="mt-2 text-sm leading-relaxed text-dark-600">La persona dejará de figurar como integrante de la Blacklist.</p>
    </div>
    <template #footer>
      <Button label="Cancelar" severity="secondary" outlined @click="confirmacionAbierta = false" />
      <Button
        label="Sí, reactivar"
        :disabled="confirmando"
        class="bg-bordo-700! hover:bg-bordo-800! text-white! border-bordo-700! shadow-sm"
        @click="confirmarReactivacion"
      />
    </template>
  </Dialog>
</template>
