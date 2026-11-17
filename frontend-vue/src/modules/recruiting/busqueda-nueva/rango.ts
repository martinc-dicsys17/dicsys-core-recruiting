/** Rango salarial: mismo formato y validación que la pantalla anterior (oportunidad_form.html). */
const RANGO_SOLO_MONTOS = /^[\d.\s$-]*$/

function formatearMonto(txt: string): string {
  const digitos = txt.replace(/\D/g, '').replace(/^0+(?=\d)/, '')
  return digitos ? `$ ${digitos.replace(/\B(?=(\d{3})+(?!\d))/g, '.')}` : ''
}

/** "2000000-3500000" -> "$ 2.000.000 - $ 3.500.000" (admite un solo importe o un guion pendiente). */
export function formatearRango(valor: string): string {
  const partes = valor.split('-')
  const desde = formatearMonto(partes[0] ?? '')
  if (!desde) return ''
  if (partes.length < 2) return desde
  const hasta = formatearMonto(partes.slice(1).join(''))
  return hasta ? `${desde} - ${hasta}` : `${desde} -`
}

/** Mensaje de error del rango, o '' si es válido. «tocado» = el campo ya perdió el foco (o se intentó guardar). */
export function errorRango(valor: string, tocado: boolean): string {
  const txt = valor.trim()
  if (!txt || !RANGO_SOLO_MONTOS.test(txt)) return ''
  const montos = txt.split('-').map((p) => parseInt(p.replace(/\D/g, ''), 10))
  if (montos.length === 2 && montos.every((n) => !isNaN(n)) && (montos[0] as number) >= (montos[1] as number)) {
    return 'El rango salarial debe ser de menor a mayor. El primer importe debe ser inferior al segundo.'
  }
  if (montos.length < 2 || montos.some((n) => isNaN(n) || n <= 0)) {
    return tocado ? 'Ingresá ambos importes del rango salarial, separados por "-".' : ''
  }
  return ''
}
