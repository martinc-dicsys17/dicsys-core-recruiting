/**
 * Datos de arranque de la SPA.
 *
 * Cuando Flask sirve la aplicacion, inyecta en el HTML los datos de la sesion actual
 * (usuario, empresa y menu) dentro de <script id="dicsys-bootstrap">. La autenticacion
 * sigue siendo la del sistema actual: la SPA no maneja tokens.
 *
 * En desarrollo (npm run dev) ese bloque viene vacio y se usa una sesion de demostracion.
 */

/** Prefijo bajo el cual Flask sirve la SPA; debe coincidir con url_prefix de modulos/vue_app. */
export const BASE_SPA = '/v2'

export interface MenuItem {
  nombre: string
  icono: string | null
  /** null = item todavia no disponible ("Prox."). */
  url: string | null
  /** true si la pantalla pertenece a la nueva interfaz Vue. */
  vue: boolean
}

export interface MenuGrupo {
  codigo: string
  nombre: string
  icono: string | null
  items: MenuItem[]
}

export interface AppBootstrap {
  origen: 'servidor' | 'demo'
  usuario: { nombre: string; email: string; rol: string; avatarUrl: string | null }
  empresa: { nombre: string; logoUrl: string | null }
  enlaces: { inicio: string; perfil: string; cerrarSesion: string }
  menus: MenuGrupo[]
}

function bootstrapDemo(): AppBootstrap {
  const legacy = import.meta.env.VITE_LEGACY_ORIGIN ?? 'http://localhost'
  const item = (nombre: string, icono: string, ruta: string): MenuItem => ({
    nombre,
    icono,
    url: `${legacy}${ruta}`,
    vue: false,
  })
  return {
    origen: 'demo',
    usuario: { nombre: 'Usuario demo', email: 'demo@ejemplo.com', rol: 'Sesion de demostracion', avatarUrl: null },
    empresa: { nombre: '', logoUrl: null },
    enlaces: {
      inicio: `${legacy}/dashboard`,
      perfil: `${legacy}/profile`,
      cerrarSesion: `${legacy}/logout`,
    },
    menus: [
      {
        codigo: 'recruiting',
        nombre: 'Recruiting',
        icono: 'user-check',
        items: [
          item('Dashboard Recruiting', 'layout-dashboard', '/recruiting/dashboard'),
          item('Candidatos', 'users', '/recruiting/candidatos'),
          { nombre: 'Blacklist', icono: 'user-x', url: `${BASE_SPA}/recruiting/blacklist`, vue: true },
        ],
      },
    ],
  }
}

export function leerBootstrap(): AppBootstrap {
  const crudo = document.getElementById('dicsys-bootstrap')?.textContent
  if (crudo) {
    try {
      const datos: unknown = JSON.parse(crudo)
      if (datos !== null && typeof datos === 'object' && 'usuario' in datos && 'menus' in datos) {
        return datos as AppBootstrap
      }
    } catch {
      // Bloque invalido: se continua con la sesion de demostracion.
    }
  }
  return bootstrapDemo()
}
