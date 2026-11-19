<script setup lang="ts">
import { Award } from '@lucide/vue'
import { ref } from 'vue'

import AbmCatalogo from './components/AbmCatalogo.vue'
import ParametrosLayout from './components/ParametrosLayout.vue'
import type { ConfigAbm } from './types'

const total = ref(0)

const config = {
  ruta: 'skills',
  claveId: 'id',
  titulo: 'Catálogo de Skills y Tecnologías',
  subtitulo: 'Tecnologías, lenguajes, frameworks y herramientas técnicas de candidatos y búsquedas',
  nuevo: 'Nuevo Skill',
  buscarPlaceholder: 'Buscar por nombre...',
  camposBusqueda: ['nombre', 'categoria'],
  cargando: 'Cargando habilidades desde la base de datos...',
  vacioTitulo: 'No se encontraron habilidades',
  vacioSinFiltro: 'No hay habilidades registradas en el catálogo.',
  vacioConFiltro: 'Probá con otro término de búsqueda.',
  columnas: [
    { clave: 'nombre', etiqueta: 'Nombre' },
    { clave: 'categoria', etiqueta: 'Categoría', tipo: 'chip' },
    { clave: 'activo', etiqueta: 'Estado', tipo: 'estado', alineacion: 'centro' },
  ],
  campos: [
    {
      clave: 'nombre',
      etiqueta: 'Nombre',
      requerido: true,
      placeholder: 'Ej: React, Python, Docker, etc.',
      ayuda: 'No se permiten nombres duplicados.',
    },
    {
      clave: 'categoria',
      etiqueta: 'Categoría',
      placeholder: 'Ej: Lenguajes, Frontend, Backend, DevOps, etc.',
      datalist: [
        'Lenguajes',
        'Frontend',
        'Backend',
        'Bases de datos',
        'DevOps & Infraestructura',
        'Cloud',
        'Data & Analytics',
        'Herramientas & Frameworks',
      ],
    },
  ],
  baja: 'logica',
  tituloEditar: 'Editar Skill',
  tituloBotonEditar: 'Editar Skill',
  tituloCrear: 'Nueva Skill',
  botonCrear: 'Crear Skill',
  textoCreado: 'Skill creado exitosamente.',
  textoActualizado: 'Skill actualizado correctamente.',
  textoBaja: (registro) => `¿Estás seguro de desactivar la skill '${registro.nombre}'? Se realizará una baja lógica.`,
  textoBajaExitosa: (registro) => `Skill '${registro.nombre}' desactivado exitosamente.`,
  textoEstado: (registro, activo) => `Skill '${registro.nombre}' ${activo ? 'activado' : 'desactivado'}.`,
  errorCargar: 'Error de conexión al cargar skills.',
  errorRequerido: 'El nombre de la habilidad es obligatorio.',
} satisfies ConfigAbm
</script>

<template>
  <ParametrosLayout activa="skills" :contadores="{ skills: total }">
    <AbmCatalogo :config="config" :icono="Award" @total="total = $event" />
  </ParametrosLayout>
</template>
