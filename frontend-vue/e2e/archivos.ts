import { crc32 } from 'node:zlib'

/** Archivos de prueba generados en memoria (sin dependencias): PDF con texto, DOCX mínimo y ZIP. Todo ficticio. */

const latin1 = (s: string) => Buffer.from(s, 'latin1')

/** PDF de una página con una línea de texto por elemento (Helvetica, texto seleccionable). */
export function crearPdf(lineas: string[]): Buffer {
  const escapar = (t: string) => t.replace(/\\/g, '\\\\').replace(/\(/g, '\\(').replace(/\)/g, '\\)')
  const contenido = ['BT', '/F1 12 Tf', '14 TL', '50 780 Td', ...lineas.map((l) => `(${escapar(l)}) Tj T*`), 'ET'].join('\n')
  const objetos = [
    '<< /Type /Catalog /Pages 2 0 R >>',
    '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
    '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>',
    `<< /Length ${Buffer.byteLength(contenido, 'latin1')} >>\nstream\n${contenido}\nendstream`,
    '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>',
  ]
  let pdf = '%PDF-1.4\n'
  const posiciones: number[] = []
  objetos.forEach((o, i) => {
    posiciones.push(Buffer.byteLength(pdf, 'latin1'))
    pdf += `${i + 1} 0 obj\n${o}\nendobj\n`
  })
  const inicioXref = Buffer.byteLength(pdf, 'latin1')
  pdf += `xref\n0 ${objetos.length + 1}\n0000000000 65535 f \n`
  for (const p of posiciones) pdf += `${String(p).padStart(10, '0')} 00000 n \n`
  pdf += `trailer\n<< /Size ${objetos.length + 1} /Root 1 0 R >>\nstartxref\n${inicioXref}\n%%EOF\n`
  return latin1(pdf)
}

/** ZIP «stored» (sin compresión) con los archivos dados. */
export function crearZip(archivos: { nombre: string; contenido: Buffer }[]): Buffer {
  const partes: Buffer[] = []
  const central: Buffer[] = []
  let desplazamiento = 0
  for (const { nombre, contenido } of archivos) {
    const nom = Buffer.from(nombre, 'utf8')
    const crc = crc32(contenido)
    const local = Buffer.alloc(30)
    local.writeUInt32LE(0x04034b50, 0)
    local.writeUInt16LE(20, 4)
    local.writeUInt16LE(0x0800, 6)
    local.writeUInt16LE(0, 8)
    local.writeUInt32LE(0x21, 10) // fecha/hora DOS arbitraria
    local.writeUInt32LE(crc >>> 0, 14)
    local.writeUInt32LE(contenido.length, 18)
    local.writeUInt32LE(contenido.length, 22)
    local.writeUInt16LE(nom.length, 26)
    local.writeUInt16LE(0, 28)
    partes.push(local, nom, contenido)
    const dir = Buffer.alloc(46)
    dir.writeUInt32LE(0x02014b50, 0)
    dir.writeUInt16LE(20, 4)
    dir.writeUInt16LE(20, 6)
    dir.writeUInt16LE(0x0800, 8)
    dir.writeUInt32LE(0x21, 12)
    dir.writeUInt32LE(crc >>> 0, 16)
    dir.writeUInt32LE(contenido.length, 20)
    dir.writeUInt32LE(contenido.length, 24)
    dir.writeUInt16LE(nom.length, 28)
    dir.writeUInt32LE(desplazamiento, 42)
    central.push(dir, nom)
    desplazamiento += local.length + nom.length + contenido.length
  }
  const tamanoCentral = central.reduce((t, b) => t + b.length, 0)
  const fin = Buffer.alloc(22)
  fin.writeUInt32LE(0x06054b50, 0)
  fin.writeUInt16LE(archivos.length, 8)
  fin.writeUInt16LE(archivos.length, 10)
  fin.writeUInt32LE(tamanoCentral, 12)
  fin.writeUInt32LE(desplazamiento, 16)
  return Buffer.concat([...partes, ...central, fin])
}

/** CV ficticio con los datos mínimos que el parser local espera (nombre, email, teléfono, puesto y skills). */
export function textoCv(c: { nombre: string; apellido: string; email: string; telefono?: string; puesto?: string; skills?: string[] }): string[] {
  return [
    `${c.nombre} ${c.apellido}`,
    c.puesto ?? 'Backend Developer',
    `Email: ${c.email}`,
    `Telefono: ${c.telefono ?? '+5493515550000'}`,
    'Ubicacion: Cordoba, Argentina',
    '',
    'Resumen profesional',
    'Desarrollador con experiencia en proyectos de software.',
    '',
    'Skills',
    (c.skills ?? ['Python', 'Django', 'SQL']).join(', '),
  ]
}
