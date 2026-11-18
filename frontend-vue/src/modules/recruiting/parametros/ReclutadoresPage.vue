<script setup lang="ts">
import { Users } from '@lucide/vue'
import { ref } from 'vue'

import AbmCatalogo from './components/AbmCatalogo.vue'
import ParametrosLayout from './components/ParametrosLayout.vue'
import type { ConfigAbm } from './types'

const total = ref(0)

const config = {
  ruta: 'reclutadores',
  claveId: 'id',
  titulo: 'Catálogo de Reclutadores responsables',
  subtitulo: 'Opciones del combo "Reclutador responsable" de Nueva oportunidad',
  nuevo: 'Nuevo Reclutador',
  buscarPlaceholder: 'Buscar por nombre...',
  camposBusqueda: ['nombre'],
  cargando: 'Cargando desde la base de datos...',
  vacioTitulo: 'No se encontraron reclutadores',
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
      placeholder: 'Ej: Ana',
      ayuda: 'No se permiten nombres duplicados. Renombrar no modifica las búsquedas ya creadas.',
    },
  ],
  baja: 'logica',
  tituloEditar: 'Editar Reclutador',
  tituloCrear: 'Nuevo Reclutador',
  botonCrear: 'Crear Reclutador',
  textoCreado: 'Reclutador creado exitosamente.',
  textoActualizado: 'Reclutador actualizado correctamente.',
  textoBaja: (registro) =>
    `¿Estás seguro de desactivar a '${registro.nombre}'? Se realizará una baja lógica: las búsquedas existentes conservan la asignación.`,
  textoBajaExitosa: (registro) => `'${registro.nombre}' desactivado exitosamente.`,
  textoEstado: (registro, activo) => `'${registro.nombre}' ${activo ? 'activado' : 'desactivado'}.`,
  errorCargar: 'Error de conexión al cargar el catálogo.',
  errorRequerido: 'El nombre es obligatorio.',
} satisfies ConfigAbm
</script>

<template>
  <ParametrosLayout activa="reclutadores" :contadores="{ reclutadores: total }">
    <AbmCatalogo :config="config" :icono="Users" @total="total = $event" />
  </ParametrosLayout>
</template>
