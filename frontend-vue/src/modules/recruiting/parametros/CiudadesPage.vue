<script setup lang="ts">
import { MapPin } from '@lucide/vue'
import { computed, ref, watch } from 'vue'

import { ErrorApi } from './api/parametros.repository'
import AbmCatalogo from './components/AbmCatalogo.vue'
import AvisoFlotante from './components/AvisoFlotante.vue'
import ParametrosLayout from './components/ParametrosLayout.vue'
import { useProvincias } from './composables/useAbm'
import { useAviso } from './composables/useAviso'
import type { ConfigAbm, Provincia } from './types'

const total = ref(0)
const provinciaId = ref('')
const { data: datosProvincias, error: errorProvincias } = useProvincias()
const provincias = computed<Provincia[]>(() =>
  (datosProvincias.value ?? []).map((provincia) => ({
    provincia_id: Number(provincia.provincia_id ?? 0),
    nombre: String(provincia.nombre ?? ''),
    cantidad_ciudades: Number(provincia.cantidad_ciudades ?? 0),
  })),
)

// Sin provincias el botón «Nueva Ciudad» queda deshabilitado: si no se pudieron cargar se avisa, como antes.
const { mensaje, tipo, notificar } = useAviso()
watch(errorProvincias, (error) => {
  if (!error) return
  notificar(
    error instanceof ErrorApi && error.estado === 0 ? 'Error de conexión al cargar las provincias.' : error.message,
    'error',
  )
})

const config = {
  ruta: 'ciudades',
  claveId: 'ciudad_id',
  titulo: 'Catálogo de Ciudades',
  subtitulo: 'Ciudades y localidades de cada provincia',
  nuevo: 'Nueva Ciudad',
  buscarPlaceholder: 'Buscar ciudad...',
  buscadorAncho: 'sm:w-56',
  camposBusqueda: ['nombre'],
  cargando: 'Cargando ciudades desde la base de datos...',
  vacioTitulo: 'No se encontraron ciudades',
  vacioSinFiltro: 'No hay ciudades registradas en el catálogo.',
  vacioConFiltro: 'Probá con otros filtros.',
  vacioSinIcono: true,
  columnas: [
    { clave: 'nombre', etiqueta: 'Ciudad' },
    { clave: 'provincia_nombre', etiqueta: 'Provincia', tipo: 'chip', vacio: '—' },
  ],
  campos: [
    { clave: 'provincia_id', etiqueta: 'Provincia', tipo: 'select', requerido: true },
    {
      clave: 'nombre',
      etiqueta: 'Nombre de la Ciudad',
      requerido: true,
      maxlength: 150,
      placeholder: 'Ej: Villa Carlos Paz',
      ayuda: 'No se permiten nombres duplicados dentro de la misma provincia, con o sin acentos.',
    },
  ],
  baja: 'fisica',
  tituloEditar: 'Editar Ciudad',
  tituloCrear: 'Nueva Ciudad',
  botonCrear: 'Crear Ciudad',
  tituloBotonEditar: 'Editar Ciudad',
  tituloBotonEliminar: 'Eliminar Ciudad',
  textoCreado: 'Ciudad creada exitosamente.',
  textoActualizado: 'Ciudad actualizada correctamente.',
  textoBaja: (registro) => `¿Estás seguro de eliminar la ciudad '${registro.nombre}'? Esta acción no se puede deshacer.`,
  textoBajaExitosa: (registro) => `Ciudad '${registro.nombre}' eliminada exitosamente.`,
  errorCargar: 'Error de conexión al cargar las ciudades.',
  errorRequerido: 'El nombre de la ciudad es obligatorio.',
  errorRequeridoSelect: 'Debe seleccionar una provincia.',
} satisfies ConfigAbm
</script>

<template>
  <ParametrosLayout activa="ciudades" :contadores="{ ciudades: total }">
    <AvisoFlotante :mensaje="mensaje" :tipo="tipo" />
    <AbmCatalogo
      v-model:provincia-id="provinciaId"
      :config="config"
      :icono="MapPin"
      :provincias="provincias"
      filtro-provincia
      @total="total = $event"
    />
  </ParametrosLayout>
</template>
