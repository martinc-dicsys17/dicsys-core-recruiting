<script setup lang="ts">
import { Award } from '@lucide/vue'
import { ref } from 'vue'

import AbmCatalogo from './components/AbmCatalogo.vue'
import ParametrosLayout from './components/ParametrosLayout.vue'
import type { ConfigAbm } from './types'

const total = ref(0)

const config = {
  ruta: 'habilidades',
  claveId: 'id',
  titulo: 'Catálogo de Habilidades y Competencias',
  subtitulo: 'Competencias profesionales y personales (soft skills) de candidatos y requisitos de búsquedas',
  nuevo: 'Nueva Habilidad',
  buscarPlaceholder: 'Buscar por competencia...',
  camposBusqueda: ['nombre', 'categoria'],
  cargando: 'Cargando habilidades desde la base de datos...',
  vacioTitulo: 'No se encontraron habilidades',
  vacioSinFiltro: 'No hay habilidades registradas en el catálogo.',
  vacioConFiltro: 'Probá con otro término de búsqueda.',
  columnas: [
    { clave: 'nombre', etiqueta: 'Nombre / Rol' },
    { clave: 'categoria', etiqueta: 'Categoría', tipo: 'chip' },
    { clave: 'activo', etiqueta: 'Estado', tipo: 'estado', alineacion: 'centro' },
  ],
  campos: [
    {
      clave: 'nombre',
      etiqueta: 'Nombre de la Competencia',
      requerido: true,
      placeholder: 'Ej: Liderazgo, Negociación, Proactividad, etc.',
      ayuda: 'No se permiten nombres duplicados.',
    },
    {
      clave: 'categoria',
      etiqueta: 'Categoría',
      placeholder: 'Ej: Comunicación, Liderazgo, Gestión, etc.',
      datalist: [
        'Comunicación',
        'Liderazgo',
        'Trabajo en equipo',
        'Resolución de problemas',
        'Adaptabilidad',
        'Organización',
        'Orientación a resultados',
      ],
    },
  ],
  baja: 'logica',
  tituloEditar: 'Editar Habilidad',
  tituloCrear: 'Nueva Habilidad',
  botonCrear: 'Crear Habilidad',
  textoCreado: 'Habilidad creada exitosamente.',
  textoActualizado: 'Habilidad actualizada correctamente.',
  textoBaja: (registro) => `¿Estás seguro de desactivar la habilidad '${registro.nombre}'? Se realizará una baja lógica.`,
  textoBajaExitosa: (registro) => `Habilidad '${registro.nombre}' desactivada exitosamente.`,
  textoEstado: (registro, activo) => `Habilidad '${registro.nombre}' ${activo ? 'activada' : 'desactivada'}.`,
  errorCargar: 'Error de conexión al cargar habilidades.',
  errorRequerido: 'El nombre de la habilidad es obligatorio.',
} satisfies ConfigAbm
</script>

<template>
  <ParametrosLayout activa="habilidades" :contadores="{ habilidades: total }">
    <AbmCatalogo :config="config" :icono="Award" @total="total = $event" />
  </ParametrosLayout>
</template>
