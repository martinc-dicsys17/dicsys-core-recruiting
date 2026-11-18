<script setup lang="ts">
import { Briefcase } from '@lucide/vue'
import { ref } from 'vue'

import AbmCatalogo from './components/AbmCatalogo.vue'
import ParametrosLayout from './components/ParametrosLayout.vue'
import type { ConfigAbm } from './types'

const total = ref(0)

const config = {
  ruta: 'perfiles-puesto',
  claveId: 'id',
  titulo: 'Catálogo de Perfiles profesionales',
  subtitulo: 'Perfiles de puesto del catálogo de Recruiting',
  nuevo: 'Nuevo Perfil',
  buscarPlaceholder: 'Buscar por nombre...',
  camposBusqueda: ['nombre'],
  cargando: 'Cargando desde la base de datos...',
  vacioTitulo: 'No se encontraron perfiles profesionales',
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
      placeholder: 'Ej: Analista de Datos',
      ayuda: 'No se permiten nombres duplicados. Renombrar no modifica candidatos ni búsquedas ya creados.',
    },
  ],
  baja: 'logica',
  tituloEditar: 'Editar Perfil profesional',
  tituloCrear: 'Nuevo Perfil profesional',
  botonCrear: 'Crear Perfil',
  textoCreado: 'Perfil profesional creado exitosamente.',
  textoActualizado: 'Perfil profesional actualizado correctamente.',
  textoBaja: (registro) =>
    `¿Estás seguro de desactivar el perfil '${registro.nombre}'? Se realizará una baja lógica: los candidatos y búsquedas existentes conservan el perfil.`,
  textoBajaExitosa: (registro) => `'${registro.nombre}' desactivado exitosamente.`,
  textoEstado: (registro, activo) => `'${registro.nombre}' ${activo ? 'activado' : 'desactivado'}.`,
  errorCargar: 'Error de conexión al cargar el catálogo.',
  errorRequerido: 'El nombre es obligatorio.',
} satisfies ConfigAbm
</script>

<template>
  <ParametrosLayout activa="perfiles" :contadores="{ perfiles: total }">
    <AbmCatalogo :config="config" :icono="Briefcase" @total="total = $event" />
  </ParametrosLayout>
</template>
