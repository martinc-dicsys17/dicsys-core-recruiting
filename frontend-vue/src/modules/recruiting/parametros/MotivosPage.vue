<script setup lang="ts">
import { ShieldBan } from '@lucide/vue'
import { ref } from 'vue'

import AbmCatalogo from './components/AbmCatalogo.vue'
import ParametrosLayout from './components/ParametrosLayout.vue'
import type { ConfigAbm } from './types'

const total = ref(0)

const config = {
  ruta: 'motivos-blacklist',
  claveId: 'id',
  titulo: 'Catálogo de Motivos de Blacklist',
  subtitulo: 'Motivos disponibles para incorporar a una persona a la Blacklist',
  nuevo: 'Nuevo Motivo',
  buscarPlaceholder: null,
  camposBusqueda: ['motivo'],
  cargando: 'Cargando motivos desde la base de datos...',
  vacioTitulo: 'No hay motivos',
  vacioSinFiltro: 'No hay motivos registrados en el catálogo.',
  vacioConFiltro: 'No hay motivos registrados en el catálogo.',
  columnas: [{ clave: 'motivo', etiqueta: 'Motivo' }],
  campos: [
    {
      clave: 'motivo',
      etiqueta: 'Motivo',
      requerido: true,
      maxlength: 150,
      placeholder: 'Ej: Conducta inapropiada',
      ayuda: 'No se permiten motivos duplicados, con o sin acentos.',
    },
  ],
  baja: 'fisica',
  tituloEditar: 'Editar Motivo',
  tituloBotonEditar: 'Editar Motivo',
  tituloBotonEliminar: 'Eliminar Motivo',
  tituloCrear: 'Nuevo Motivo',
  botonCrear: 'Crear Motivo',
  textoCreado: 'Motivo creado exitosamente.',
  textoActualizado: 'Motivo actualizado correctamente.',
  textoBaja: (registro) => `¿Estás seguro de eliminar el motivo '${registro.motivo}'? Esta acción no se puede deshacer.`,
  textoBajaExitosa: (registro) => `Motivo '${registro.motivo}' eliminado exitosamente.`,
  errorCargar: 'Error de conexión al cargar los motivos.',
  errorRequerido: 'El nombre del motivo es obligatorio.',
  vacioSimple: true,
} satisfies ConfigAbm
</script>

<template>
  <ParametrosLayout activa="motivos" :contadores="{ motivos: total }">
    <AbmCatalogo :config="config" :icono="ShieldBan" @total="total = $event" />
  </ParametrosLayout>
</template>
