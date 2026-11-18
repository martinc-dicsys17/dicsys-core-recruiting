import { onScopeDispose, ref } from 'vue'

export type TipoAviso = 'exito' | 'error'

/**
 * Aviso flotante de la pantalla (el toast de la interfaz anterior): aparece arriba a la derecha y se cierra solo.
 * El texto y el tipo se reemplazan en cada notificación.
 */
export function useAviso() {
  const mensaje = ref('')
  const tipo = ref<TipoAviso>('exito')
  let temporizador: number | undefined

  function notificar(texto: string, nuevoTipo: TipoAviso = 'exito', duracion = 3500): void {
    window.clearTimeout(temporizador)
    mensaje.value = texto
    tipo.value = nuevoTipo
    temporizador = window.setTimeout(() => {
      mensaje.value = ''
    }, duracion)
  }

  onScopeDispose(() => window.clearTimeout(temporizador))

  return { mensaje, tipo, notificar }
}
