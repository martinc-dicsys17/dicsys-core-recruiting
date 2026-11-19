<script setup lang="ts">
import { Map } from '@lucide/vue'
import { ref } from 'vue'

import AbmCatalogo from './components/AbmCatalogo.vue'
import ParametrosLayout from './components/ParametrosLayout.vue'
import type { ConfigAbm } from './types'

const total = ref(0)

const config = {
  ruta: 'provincias',
  claveId: 'provincia_id',
  titulo: 'Catálogo de Provincias',
  subtitulo: 'Provincias disponibles para la ubicación de candidatos',
  nuevo: 'Nueva Provincia',
  buscarPlaceholder: null,
  camposBusqueda: ['nombre'],
  cargando: 'Cargando provincias desde la base de datos...',
  vacioTitulo: 'No hay provincias',
  vacioSinFiltro: 'No hay provincias registradas en el catálogo.',
  vacioConFiltro: 'No hay provincias registradas en el catálogo.',
  columnas: [
    { clave: 'nombre', etiqueta: 'Provincia' },
    { clave: 'cantidad_ciudades', etiqueta: 'Ciudades', tipo: 'contador', alineacion: 'centro' },
  ],
  campos: [
    {
      clave: 'nombre',
      etiqueta: 'Nombre de la Provincia',
      requerido: true,
      maxlength: 100,
      placeholder: 'Ej: Cordoba',
      ayuda: 'No se permiten nombres duplicados, con o sin acentos.',
    },
  ],
  baja: 'fisica',
  tituloEditar: 'Editar Provincia',
  tituloBotonEditar: 'Editar Provincia',
  tituloBotonEliminar: 'Eliminar Provincia',
  tituloCrear: 'Nueva Provincia',
  botonCrear: 'Crear Provincia',
  textoCreado: 'Provincia creada exitosamente.',
  textoActualizado: 'Provincia actualizada correctamente.',
  textoBaja: (registro) => `¿Estás seguro de eliminar la provincia '${registro.nombre}'? Esta acción no se puede deshacer.`,
  textoBajaExitosa: (registro) => `Provincia '${registro.nombre}' eliminada exitosamente.`,
  errorCargar: 'Error de conexión al cargar las provincias.',
  errorRequerido: 'El nombre de la provincia es obligatorio.',
  vacioSimple: true,
} satisfies ConfigAbm
</script>

<template>
  <ParametrosLayout activa="provincias" :contadores="{ provincias: total }">
    <AbmCatalogo :config="config" :icono="Map" @total="total = $event" />
  </ParametrosLayout>
</template>
