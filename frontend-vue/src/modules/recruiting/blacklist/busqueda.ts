/** Utilidades de busqueda de Blacklist: comparacion sin tildes y por digitos (DNI y telefono). */

/** Minimo de digitos para buscar por telefono (evita coincidencias con numeros demasiado cortos). */
export const MIN_DIGITOS_TELEFONO = 4

/** Compara sin distinguir mayusculas ni tildes. */
export function normalizarTexto(texto: string): string {
  return texto
    .normalize('NFD')
    .replace(/\p{Diacritic}/gu, '')
    .toLowerCase()
}

/** Deja solo los digitos (ignora puntos, espacios, guiones, parentesis y signos). */
export function soloDigitos(texto: string | null | undefined): string {
  return (texto ?? '').replace(/\D/g, '')
}

/** Quita el prefijo internacional de Argentina (+54, 54 o +54 9) si el usuario lo escribio. */
export function quitarPrefijoPais(termino: string, digitos: string): string {
  const conMas = /^\s*(\+|00)/.test(termino)
  if (conMas || digitos.length >= 12) {
    const sinPais = digitos.replace(/^(00)?54/, '')
    if (sinPais !== digitos) return sinPais.replace(/^9(?=\d{10}$)/, '')
  }
  return digitos
}

/** Indica si el termino (ya normalizado) coincide con el DNI o el telefono comparando solo digitos. */
export function coincidePorDigitos(
  termino: string,
  documento: string | null | undefined,
  telefono: string | null | undefined,
): boolean {
  if (/[\p{L}@]/u.test(termino)) return false
  const digitos = soloDigitos(termino)
  if (!digitos) return false
  if (soloDigitos(documento).includes(digitos)) return true
  const local = quitarPrefijoPais(termino, digitos)
  return local.length >= MIN_DIGITOS_TELEFONO && soloDigitos(telefono).includes(local)
}
