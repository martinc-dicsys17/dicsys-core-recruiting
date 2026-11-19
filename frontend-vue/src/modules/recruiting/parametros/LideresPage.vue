<script setup lang="ts">
import { UserCheck } from '@lucide/vue'
import { ref } from 'vue'

import AbmCatalogo from './components/AbmCatalogo.vue'
import ParametrosLayout from './components/ParametrosLayout.vue'
import type { ConfigAbm } from './types'

const total = ref(0)

const config = {
  ruta: 'lideres',
  claveId: 'id',
  titulo: 'Catálogo de Líderes / Hiring Managers',
  subtitulo: 'Opciones del combo “Líder / Hiring Manager” de Nueva oportunidad',
  nuevo: 'Nuevo Líder',
  buscarPlaceholder: 'Buscar por nombre...',
  camposBusqueda: ['nombre'],
  cargando: 'Cargando desde la base de datos...',
  vacioTitulo: 'No se encontraron líderes',
  vacioSinFiltro: 'No hay registros cargados en el catálogo.',
  vacioConFiltro: 'Probá con otro término de búsqueda.',
  columnas: [
    { clave: 'nombre', etiqueta: 'Nombre' },
    { clave: 'activo', etiqueta: 'Estado', tipo: 'estado', alineacion: 'centro' },
  ],
  campos: [
    {
      clave: 'nombre',
      etiqueta: 'Nombre',
      requerido: true,
      maxlength: 150,
      placeholder: 'Ej: Maria Jose Padin',
      ayuda: 'No se permiten nombres duplicados. Renombrar no modifica las búsquedas ya creadas.',
    },
  ],
  baja: 'logica',
  tituloEditar: 'Editar Líder',
  tituloCrear: 'Nuevo Líder',
  botonCrear: 'Crear Líder',
  textoCreado: 'Líder creado exitosamente.',
  textoActualizado: 'Líder actualizado correctamente.',
  textoBaja: (registro) =>
    `¿Estás seguro de desactivar a '${registro.nombre}'? Se realizará una baja lógica: las búsquedas existentes conservan la asignación.`,
  textoBajaExitosa: (registro) => `'${registro.nombre}' desactivado exitosamente.`,
  textoEstado: (registro, activo) => `'${registro.nombre}' ${activo ? 'activado' : 'desactivado'}.`,
  errorCargar: 'Error de conexión al cargar el catálogo.',
  errorRequerido: 'El nombre es obligatorio.',
} satisfies ConfigAbm
</script>

<template>
  <ParametrosLayout activa="lideres" :contadores="{ lideres: total }">
    <AbmCatalogo :config="config" :icono="UserCheck" @total="total = $event" />
  </ParametrosLayout>
</template>
